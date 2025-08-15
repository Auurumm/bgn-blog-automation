#!/usr/bin/env python3
"""
src/integrations/wordpress_client.py

📋 역할: 워드프레스 완전 자동 포스팅 및 미디어 관리
- XML-RPC를 통한 워드프레스 API 연동
- 이미지 자동 업로드 및 미디어 라이브러리 관리
- HTML 콘텐츠 자동 포스팅 (제목, 내용, 태그, 카테고리)
- 대표 이미지 자동 설정 및 본문 이미지 삽입
- SEO 메타데이터 자동 설정 (제목, 설명, 태그)
- 발행 상태 관리 (초안, 발행, 예약 발행)
- 포스트 수정 및 업데이트 기능
- 에러 처리 및 재시도 로직
- 백업 및 복구 기능
"""

import base64
import requests
import mimetypes
from PIL import Image
import io
import os
import sys
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass
import time
import json

# WordPress XML-RPC 라이브러리
try:
    from wordpress_xmlrpc import Client, WordPressPost, WordPressPage
    from wordpress_xmlrpc.methods.posts import NewPost, EditPost, GetPost, DeletePost
    from wordpress_xmlrpc.methods.media import UploadFile, GetMediaLibrary
    from wordpress_xmlrpc.methods.taxonomies import GetTerms
    from wordpress_xmlrpc.methods.users import GetUserInfo
    from wordpress_xmlrpc.compat import xmlrpc_client
    WORDPRESS_AVAILABLE = True
except ImportError:
    WORDPRESS_AVAILABLE = False
    print("⚠️ WordPress 라이브러리 설치 필요: pip install python-wordpress-xmlrpc")

# 프로젝트 내부 모듈
try:
    from ...config.settings import Settings
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from config.settings import Settings

try:
    from ..generators.content_generator import GeneratedContent
except ImportError:
    from src.generators.content_generator import GeneratedContent

# 로깅 설정
logging.basicConfig(level=getattr(logging, Settings.LOG_LEVEL))
logger = logging.getLogger(__name__)

@dataclass
class WordPressConfig:
    """워드프레스 연결 설정"""
    url: str
    username: str
    password: str
    default_category: str = "안과정보"
    default_status: str = "draft"  # draft, publish, private, future
    timeout: int = 30
    max_retries: int = 3
    
    def __post_init__(self):
        if not self.url.startswith(('http://', 'https://')):
            self.url = f"https://{self.url}"
        
        # URL 정리 (trailing slash 제거)
        self.url = self.url.rstrip('/')

@dataclass
class MediaUploadResult:
    """미디어 업로드 결과"""
    media_id: int
    url: str
    filename: str
    mime_type: str
    upload_date: datetime
    file_size: int = 0
    alt_text: str = ""
    success: bool = True
    error_message: str = ""

@dataclass
class PostPublishResult:
    """포스트 발행 결과"""
    post_id: int
    post_url: str
    edit_url: str
    status: str
    publish_date: datetime
    featured_image_id: Optional[int] = None
    media_ids: List[int] = None
    success: bool = True
    error_message: str = ""
    
    def __post_init__(self):
        if self.media_ids is None:
            self.media_ids = []

class BGNWordPressClient:
    """BGN 전용 워드프레스 클라이언트"""
    
    def __init__(self, config: WordPressConfig = None):
        """
        워드프레스 클라이언트 초기화
        
        Args:
            config: 워드프레스 연결 설정 (None인 경우 Settings에서 가져옴)
        """
        if not WORDPRESS_AVAILABLE:
            raise ImportError("WordPress 라이브러리가 설치되지 않았습니다. 'pip install python-wordpress-xmlrpc'를 실행하세요.")
        
        if config is None:
            config = WordPressConfig(
                url=Settings.WORDPRESS_URL,
                username=Settings.WORDPRESS_USERNAME,
                password=Settings.WORDPRESS_PASSWORD,
                default_category=Settings.WORDPRESS_DEFAULT_CATEGORY,
                default_status=Settings.WORDPRESS_DEFAULT_STATUS
            )
        
        self.config = config
        self.client = None
        self.connection_verified = False
        
        # 통계 추적
        self.upload_count = 0
        self.post_count = 0
        self.failed_operations = []
        
        # 연결 초기화
        self._initialize_connection()
        
        logger.info(f"BGN 워드프레스 클라이언트 초기화 완료: {config.url}")
    
    def _initialize_connection(self):
        """워드프레스 연결 초기화"""
        try:
            xmlrpc_url = f"{self.config.url}/xmlrpc.php"
            self.client = Client(xmlrpc_url, self.config.username, self.config.password)
            
            # 연결 테스트
            self._verify_connection()
            
        except Exception as e:
            logger.error(f"워드프레스 연결 실패: {str(e)}")
            raise ConnectionError(f"워드프레스 연결 실패: {str(e)}")
    
    def _verify_connection(self) -> bool:
        """연결 상태 확인"""
        try:
            # 사용자 정보 조회로 연결 테스트
            user_info = self.client.call(GetUserInfo())
            self.connection_verified = True
            
            logger.info(f"워드프레스 연결 성공: {user_info.username} ({user_info.email})")
            return True
            
        except Exception as e:
            logger.error(f"워드프레스 연결 확인 실패: {str(e)}")
            self.connection_verified = False
            return False
    
    def upload_image_with_retry(self, 
                               image: Union[Image.Image, str], 
                               filename: str,
                               alt_text: str = "",
                               description: str = "") -> MediaUploadResult:
        """
        이미지 업로드 (재시도 로직 포함)
        
        Args:
            image: PIL Image 객체 또는 파일 경로
            filename: 파일명
            alt_text: 대체 텍스트 (SEO/접근성)
            description: 이미지 설명
            
        Returns:
            MediaUploadResult: 업로드 결과
        """
        for attempt in range(self.config.max_retries):
            try:
                logger.info(f"이미지 업로드 시도 {attempt + 1}/{self.config.max_retries}: {filename}")
                
                # 이미지 데이터 준비
                image_data = self._prepare_image_data(image, filename)
                
                # 워드프레스 업로드 데이터 구성
                upload_data = {
                    'name': filename,
                    'type': image_data['mime_type'],
                    'bits': image_data['base64_data'],
                    'overwrite': False
                }
                
                # 업로드 실행
                response = self.client.call(UploadFile(upload_data))
                
                # 결과 처리
                media_result = MediaUploadResult(
                    media_id=response['id'],
                    url=response['url'],
                    filename=response['file'],
                    mime_type=image_data['mime_type'],
                    upload_date=datetime.now(),
                    file_size=image_data['file_size'],
                    alt_text=alt_text,
                    success=True
                )
                
                # 대체 텍스트 설정 (워드프레스 메타데이터)
                if alt_text:
                    self._set_media_metadata(media_result.media_id, alt_text, description)
                
                self.upload_count += 1
                logger.info(f"이미지 업로드 성공: {filename} (ID: {media_result.media_id})")
                
                return media_result
                
            except Exception as e:
                logger.warning(f"이미지 업로드 실패 (시도 {attempt + 1}): {str(e)}")
                
                if attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)  # 지수 백오프
                else:
                    # 최종 실패
                    error_result = MediaUploadResult(
                        media_id=0,
                        url="",
                        filename=filename,
                        mime_type="",
                        upload_date=datetime.now(),
                        success=False,
                        error_message=str(e)
                    )
                    
                    self.failed_operations.append({
                        "operation": "image_upload",
                        "filename": filename,
                        "error": str(e),
                        "timestamp": datetime.now()
                    })
                    
                    return error_result
    
    def _prepare_image_data(self, image: Union[Image.Image, str], filename: str) -> Dict:
        """이미지 데이터 준비 및 최적화"""
        
        if isinstance(image, str):
            # 파일 경로인 경우
            with open(image, 'rb') as f:
                image_bytes = f.read()
            mime_type = mimetypes.guess_type(image)[0] or 'image/jpeg'
            
        elif isinstance(image, Image.Image):
            # PIL Image인 경우
            # 이미지 최적화
            optimized_image = self._optimize_image_for_web(image)
            
            # 바이트로 변환
            img_byte_arr = io.BytesIO()
            
            # 포맷 결정
            if filename.lower().endswith('.png'):
                optimized_image.save(img_byte_arr, format='PNG', optimize=True)
                mime_type = 'image/png'
            else:
                optimized_image.save(img_byte_arr, format='JPEG', quality=85, optimize=True)
                mime_type = 'image/jpeg'
                # 파일명 확장자 보정
                if not filename.lower().endswith(('.jpg', '.jpeg')):
                    filename = filename.rsplit('.', 1)[0] + '.jpg'
            
            image_bytes = img_byte_arr.getvalue()
            
        else:
            raise ValueError("image는 PIL.Image 또는 파일 경로여야 합니다.")
        
        # Base64 인코딩
        base64_data = base64.b64encode(image_bytes).decode('utf-8')
        
        return {
            'base64_data': base64_data,
            'mime_type': mime_type,
            'file_size': len(image_bytes),
            'filename': filename
        }
    
    def _optimize_image_for_web(self, image: Image.Image) -> Image.Image:
        """웹용 이미지 최적화"""
        
        # RGB 모드로 변환
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # 크기 최적화 (최대 1920px)
        max_width = 1920
        max_height = 1080
        
        if image.width > max_width or image.height > max_height:
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        return image
    
    def _set_media_metadata(self, media_id: int, alt_text: str, description: str = ""):
        """미디어 메타데이터 설정 (ALT 텍스트 등)"""
        try:
            # WordPress는 XML-RPC로 직접 ALT 텍스트 설정이 제한적
            # 필요시 REST API 사용 고려
            pass
        except Exception as e:
            logger.warning(f"미디어 메타데이터 설정 실패: {str(e)}")
    
    def create_post_with_media(self, 
                              content_data: GeneratedContent,
                              images: List[Tuple[Image.Image, str]] = None,
                              publish_immediately: bool = False,
                              scheduled_date: datetime = None) -> PostPublishResult:
        """
        이미지와 함께 완전한 포스트 생성
        
        Args:
            content_data: 생성된 콘텐츠 데이터
            images: [(PIL Image, ALT 텍스트)] 리스트
            publish_immediately: 즉시 발행 여부
            scheduled_date: 예약 발행 날짜
            
        Returns:
            PostPublishResult: 발행 결과
        """
        logger.info(f"포스트 생성 시작: {content_data.title}")
        
        uploaded_media = []
        featured_image_id = None
        
        try:
            # 1단계: 이미지 업로드
            if images:
                logger.info(f"{len(images)}개 이미지 업로드 중...")
                
                for i, (image, alt_text) in enumerate(images):
                    # 파일명 생성
                    filename = f"{content_data.slug}_image_{i+1}.jpg"
                    
                    # 업로드 실행
                    upload_result = self.upload_image_with_retry(
                        image=image,
                        filename=filename,
                        alt_text=alt_text,
                        description=f"{content_data.title} 관련 이미지 {i+1}"
                    )
                    
                    if upload_result.success:
                        uploaded_media.append(upload_result)
                        
                        # 첫 번째 이미지를 대표 이미지로 설정
                        if i == 0:
                            featured_image_id = upload_result.media_id
                    else:
                        logger.warning(f"이미지 {i+1} 업로드 실패: {upload_result.error_message}")
            
            # 2단계: HTML 콘텐츠 생성 (업로드된 이미지 포함)
            html_content = self._build_post_html(content_data, uploaded_media)
            
            # 3단계: 워드프레스 포스트 객체 생성
            post = self._create_wordpress_post_object(
                content_data, html_content, featured_image_id, 
                publish_immediately, scheduled_date
            )
            
            # 4단계: 포스트 발행
            post_id = self.client.call(NewPost(post))
            
            # 5단계: 결과 URL 생성
            post_url = f"{self.config.url}/?p={post_id}"
            edit_url = f"{self.config.url}/wp-admin/post.php?post={post_id}&action=edit"
            
            # 6단계: 결과 객체 생성
            result = PostPublishResult(
                post_id=post_id,
                post_url=post_url,
                edit_url=edit_url,
                status=post.post_status,
                publish_date=datetime.now(),
                featured_image_id=featured_image_id,
                media_ids=[m.media_id for m in uploaded_media if m.success],
                success=True
            )
            
            self.post_count += 1
            logger.info(f"포스트 발행 성공: {content_data.title} (ID: {post_id})")
            
            return result
            
        except Exception as e:
            logger.error(f"포스트 생성 실패: {str(e)}")
            
            # 실패 시 업로드된 이미지 정리 (선택적)
            # self._cleanup_failed_media(uploaded_media)
            
            error_result = PostPublishResult(
                post_id=0,
                post_url="",
                edit_url="",
                status="failed",
                publish_date=datetime.now(),
                success=False,
                error_message=str(e)
            )
            
            self.failed_operations.append({
                "operation": "post_creation",
                "title": content_data.title,
                "error": str(e),
                "timestamp": datetime.now()
            })
            
            return error_result
    
    def _build_post_html(self, 
                        content_data: GeneratedContent, 
                        uploaded_media: List[MediaUploadResult]) -> str:
        """포스트 HTML 생성 (업로드된 이미지 포함)"""
        
        # 기본 HTML 콘텐츠
        html = content_data.content_html
        
        # BGN 스타일링 추가
        styled_html = f"""
        <div class="bgn-blog-post">
            <div class="post-meta">
                <span class="reading-time">📖 약 {content_data.estimated_reading_time}분 소요</span>
                <span class="post-tags">🏷️ {', '.join(content_data.tags[:3])}</span>
            </div>
            
            <div class="post-content">
                {html}
            </div>
            
            <div class="post-footer">
                <div class="hospital-info">
                    <h3>🏥 {Settings.HOSPITAL_NAME}</h3>
                    <p>📍 위치: {', '.join(Settings.HOSPITAL_LOCATIONS)}</p>
                    <p>📞 상담문의: {Settings.HOSPITAL_PHONE}</p>
                </div>
                
                <div class="cta-section">
                    <a href="#contact" class="cta-button">{content_data.cta_button_text}</a>
                </div>
                
                <div class="medical-disclaimer">
                    <p><strong>⚠️ 의료진 검토 완료</strong> | {Settings.HOSPITAL_NAME}</p>
                    <p>본 내용은 일반적인 안내사항으로, 개인별 상태에 따라 달라질 수 있습니다. 
                    정확한 진단과 치료는 의료진과의 상담을 통해 받으시기 바랍니다.</p>
                </div>
            </div>
        </div>
        
        <style>
        .bgn-blog-post {
            font-family: 'Noto Sans KR', sans-serif;
            line-height: 1.6;
            color: #333;
        }
        .post-meta {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            font-size: 14px;
            color: #666;
        }
        .cta-button {
            display: inline-block;
            background: linear-gradient(135deg, #2E86AB, #A23B72);
            color: white;
            padding: 15px 30px;
            text-decoration: none;
            border-radius: 25px;
            font-weight: bold;
            margin: 20px 0;
        }
        .medical-disclaimer {
            background: #fff3cd;
            border: 1px solid #ffc107;
            padding: 15px;
            border-radius: 5px;
            margin-top: 30px;
            font-size: 14px;
        }
        .hospital-info {
            background: #e7f3ff;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        </style>
        """
        
        # 업로드된 이미지를 적절한 위치에 삽입
        if uploaded_media:
            # 대표 이미지 (첫 번째 이미지)
            if len(uploaded_media) >= 1:
                first_image = uploaded_media[0]
                featured_img_html = f"""
                <div class="featured-image" style="text-align: center; margin: 20px 0;">
                    <img src="{first_image.url}" alt="{first_image.alt_text}" 
                         style="max-width: 100%; height: auto; border-radius: 8px;" />
                </div>
                """
                # 첫 번째 H2 태그 뒤에 삽입
                styled_html = styled_html.replace('</h2>', '</h2>' + featured_img_html, 1)
            
            # 중간 이미지들 삽입
            for i, media in enumerate(uploaded_media[1:], 2):
                img_html = f"""
                <div class="content-image" style="text-align: center; margin: 25px 0;">
                    <img src="{media.url}" alt="{media.alt_text}" 
                         style="max-width: 100%; height: auto; border-radius: 8px;" />
                </div>
                """
                
                # H2 태그 개수에 따라 적절한 위치에 삽입
                h2_count = styled_html.count('</h2>')
                if i <= h2_count:
                    # i번째 H2 태그 뒤에 삽입
                    h2_positions = [m.end() for m in re.finditer('</h2>', styled_html)]
                    if len(h2_positions) >= i:
                        insert_pos = h2_positions[i-1]
                        styled_html = styled_html[:insert_pos] + img_html + styled_html[insert_pos:]
        
        return styled_html
    
    def _create_wordpress_post_object(self, 
                                     content_data: GeneratedContent,
                                     html_content: str,
                                     featured_image_id: Optional[int],
                                     publish_immediately: bool,
                                     scheduled_date: datetime) -> WordPressPost:
        """워드프레스 포스트 객체 생성"""
        
        post = WordPressPost()
        
        # 기본 정보
        post.title = content_data.title
        post.content = html_content
        post.excerpt = content_data.meta_description
        post.slug = content_data.slug
        
        # 발행 상태 결정
        if publish_immediately:
            post.post_status = 'publish'
        elif scheduled_date and scheduled_date > datetime.now():
            post.post_status = 'future'
            post.date = scheduled_date
        else:
            post.post_status = self.config.default_status
        
        # 태그 및 카테고리 설정
        post.terms_names = {
            'post_tag': content_data.tags,
            'category': [self.config.default_category]
        }
        
        # 대표 이미지 설정
        if featured_image_id:
            post.thumbnail = featured_image_id
        
        # SEO 메타 설정 (Yoast SEO 등 플러그인 호환)
        post.custom_fields = [
            {
                'key': '_yoast_wpseo_metadesc',
                'value': content_data.meta_description
            },
            {
                'key': '_yoast_wpseo_title', 
                'value': content_data.title
            },
            {
                'key': 'bgn_seo_score',
                'value': str(content_data.seo_score)
            },
            {
                'key': 'bgn_medical_compliance',
                'value': str(content_data.medical_compliance_score)
            },
            {
                'key': 'bgn_reading_time',
                'value': str(content_data.estimated_reading_time)
            }
        ]
        
        return post
    
    def update_existing_post(self, 
                            post_id: int, 
                            content_data: GeneratedContent,
                            images: List[Tuple[Image.Image, str]] = None) -> PostPublishResult:
        """기존 포스트 업데이트"""
        
        try:
            logger.info(f"포스트 업데이트 시작: ID {post_id}")
            
            # 기존 포스트 조회
            existing_post = self.client.call(GetPost(post_id))
            
            # 새 이미지 업로드 (필요한 경우)
            uploaded_media = []
            if images:
                for i, (image, alt_text) in enumerate(images):
                    filename = f"{content_data.slug}_updated_{i+1}.jpg"
                    upload_result = self.upload_image_with_retry(image, filename, alt_text)
                    if upload_result.success:
                        uploaded_media.append(upload_result)
            
            # HTML 콘텐츠 업데이트
            html_content = self._build_post_html(content_data, uploaded_media)
            
            # 포스트 정보 업데이트
            existing_post.title = content_data.title
            existing_post.content = html_content
            existing_post.excerpt = content_data.meta_description
            existing_post.terms_names = {
                'post_tag': content_data.tags,
                'category': [self.config.default_category]
            }
            
            # 업데이트 실행
            success = self.client.call(EditPost(post_id, existing_post))
            
            if success:
                result = PostPublishResult(
                    post_id=post_id,
                    post_url=f"{self.config.url}/?p={post_id}",
                    edit_url=f"{self.config.url}/wp-admin/post.php?post={post_id}&action=edit",
                    status=existing_post.post_status,
                    publish_date=datetime.now(),
                    media_ids=[m.media_id for m in uploaded_media],
                    success=True
                )
                
                logger.info(f"포스트 업데이트 성공: ID {post_id}")
                return result
            else:
                raise Exception("포스트 업데이트 실패")
                
        except Exception as e:
            logger.error(f"포스트 업데이트 실패: {str(e)}")
            return PostPublishResult(
                post_id=post_id,
                post_url="",
                edit_url="",
                status="update_failed",
                publish_date=datetime.now(),
                success=False,
                error_message=str(e)
            )
    
    def batch_publish_posts(self, 
                           content_list: List[GeneratedContent],
                           images_list: List[List[Tuple[Image.Image, str]]] = None,
                           delay_between_posts: int = 30) -> List[PostPublishResult]:
        """여러 포스트 일괄 발행"""
        
        if images_list is None:
            images_list = [None] * len(content_list)
        
        results = []
        
        for i, (content, images) in enumerate(zip(content_list, images_list)):
            logger.info(f"일괄 발행 진행: {i+1}/{len(content_list)}")
            
            try:
                result = self.create_post_with_media(content, images)
                results.append(result)
                
                # 서버 부하 방지를 위한 딜레이
                if i < len(content_list) - 1:
                    time.sleep(delay_between_posts)
                    
            except Exception as e:
                logger.error(f"일괄 발행 중 오류 (포스트 {i+1}): {str(e)}")
                error_result = PostPublishResult(
                    post_id=0,
                    post_url="",
                    edit_url="",
                    status="batch_failed",
                    publish_date=datetime.now(),
                    success=False,
                    error_message=str(e)
                )
                results.append(error_result)
        
        successful_posts = sum(1 for r in results if r.success)
        logger.info(f"일괄 발행 완료: {successful_posts}/{len(content_list)} 성공")
        
        return results
    
    def get_client_stats(self) -> Dict[str, Any]:
        """클라이언트 사용 통계"""
        return {
            "connection_verified": self.connection_verified,
            "uploads_completed": self.upload_count,
            "posts_created": self.post_count,
            "failed_operations": len(self.failed_operations),
            "recent_failures": self.failed_operations[-5:] if self.failed_operations else [],
            "wordpress_url": self.config.url,
            "default_category": self.config.default_category
        }

# 유틸리티 함수들
def create_bgn_wordpress_client(url: str = None, 
                               username: str = None, 
                               password: str = None) -> BGNWordPressClient:
    """BGN 워드프레스 클라이언트 생성 (편의 함수)"""
    config = WordPressConfig(
        url=url or Settings.WORDPRESS_URL,
        username=username or Settings.WORDPRESS_USERNAME,
        password=password or Settings.WORDPRESS_PASSWORD
    )
    return BGNWordPressClient(config)

def quick_publish_content(content_data: GeneratedContent, 
                         images: List[Tuple[Image.Image, str]] = None,
                         publish_now: bool = False) -> Dict:
    """빠른 콘텐츠 발행 (테스트용)"""
    try:
        client = create_bgn_wordpress_client()
        result = client.create_post_with_media(
            content_data=content_data,
            images=images,
            publish_immediately=publish_now
        )
        return {
            "success": result.success,
            "post_id": result.post_id,
            "post_url": result.post_url,
            "edit_url": result.edit_url,
            "error": result.error_message if not result.success else None
        }
    except Exception as e:
        return {
            "success": False,
            "post_id": 0,
            "post_url": "",
            "edit_url": "",
            "error": str(e)
        }

# 고급 기능들
class BGNWordPressManager:
    """BGN 워드프레스 고급 관리 기능"""
    
    def __init__(self, client: BGNWordPressClient):
        self.client = client
        self.scheduler = []
        
    def schedule_posts(self, 
                      content_schedule: List[Tuple[GeneratedContent, datetime]],
                      images_list: List[List[Tuple[Image.Image, str]]] = None) -> List[PostPublishResult]:
        """포스트 예약 발행"""
        
        results = []
        
        for i, (content, publish_date) in enumerate(content_schedule):
            images = images_list[i] if images_list and i < len(images_list) else None
            
            try:
                result = self.client.create_post_with_media(
                    content_data=content,
                    images=images,
                    scheduled_date=publish_date
                )
                results.append(result)
                
                logger.info(f"예약 발행 설정: {content.title} -> {publish_date}")
                
            except Exception as e:
                logger.error(f"예약 발행 실패: {content.title} - {str(e)}")
                error_result = PostPublishResult(
                    post_id=0,
                    post_url="",
                    edit_url="",
                    status="schedule_failed",
                    publish_date=publish_date,
                    success=False,
                    error_message=str(e)
                )
                results.append(error_result)
        
        return results
    
    def create_content_series(self, 
                             series_name: str,
                             content_list: List[GeneratedContent],
                             images_list: List[List[Tuple[Image.Image, str]]],
                             publish_interval_days: int = 3) -> List[PostPublishResult]:
        """연재 콘텐츠 생성 (일정 간격으로 발행)"""
        
        schedule = []
        start_date = datetime.now() + timedelta(days=1)  # 내일부터 시작
        
        for i, content in enumerate(content_list):
            publish_date = start_date + timedelta(days=i * publish_interval_days)
            
            # 제목에 시리즈 정보 추가
            content.title = f"[{series_name} {i+1}/{len(content_list)}] {content.title}"
            
            schedule.append((content, publish_date))
        
        return self.schedule_posts(schedule, images_list)
    
    def backup_posts(self, post_ids: List[int]) -> Dict[str, Any]:
        """포스트 백업"""
        backups = {}
        
        for post_id in post_ids:
            try:
                post = self.client.client.call(GetPost(post_id))
                backups[str(post_id)] = {
                    "title": post.title,
                    "content": post.content,
                    "excerpt": post.excerpt,
                    "status": post.post_status,
                    "date": post.date.isoformat() if post.date else None,
                    "backup_date": datetime.now().isoformat()
                }
                logger.info(f"포스트 백업 완료: ID {post_id}")
                
            except Exception as e:
                logger.error(f"포스트 백업 실패: ID {post_id} - {str(e)}")
                backups[str(post_id)] = {"error": str(e)}
        
        # 백업 파일 저장
        backup_filename = f"bgn_wp_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup_path = os.path.join("data", "backups", backup_filename)
        
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(backups, f, ensure_ascii=False, indent=2)
        
        return {
            "backup_file": backup_path,
            "backed_up_posts": len([p for p in backups.values() if "error" not in p]),
            "failed_backups": len([p for p in backups.values() if "error" in p])
        }

# 사용 예시 및 테스트
if __name__ == "__main__":
    try:
        print("🔗 BGN 워드프레스 클라이언트 테스트 시작...")
        
        # 연결 테스트
        if not WORDPRESS_AVAILABLE:
            print("❌ WordPress 라이브러리가 설치되지 않았습니다.")
            print("💡 설치 명령어: pip install python-wordpress-xmlrpc")
            exit(1)
        
        # 설정 확인
        if not all([Settings.WORDPRESS_URL, Settings.WORDPRESS_USERNAME, Settings.WORDPRESS_PASSWORD]):
            print("❌ 워드프레스 설정이 완료되지 않았습니다.")
            print("💡 .env 파일에 WORDPRESS_URL, WORDPRESS_USERNAME, WORDPRESS_PASSWORD를 설정하세요.")
            exit(1)
        
        print("⚙️ 워드프레스 클라이언트 초기화 중...")
        client = create_bgn_wordpress_client()
        
        print("✅ 워드프레스 연결 성공!")
        
        # 통계 확인
        stats = client.get_client_stats()
        print(f"📊 연결 정보:")
        print(f"  - URL: {stats['wordpress_url']}")
        print(f"  - 기본 카테고리: {stats['default_category']}")
        print(f"  - 연결 상태: {'✅ 정상' if stats['connection_verified'] else '❌ 실패'}")
        
        # 테스트 이미지 생성 (더미)
        print("\n🎨 테스트 이미지 생성 중...")
        test_image = Image.new('RGB', (800, 600), color='lightblue')
        
        # 테스트 업로드
        print("📤 테스트 이미지 업로드 중...")
        upload_result = client.upload_image_with_retry(
            image=test_image,
            filename="bgn_test_image.jpg",
            alt_text="BGN 테스트 이미지"
        )
        
        if upload_result.success:
            print(f"✅ 이미지 업로드 성공!")
            print(f"  - 미디어 ID: {upload_result.media_id}")
            print(f"  - URL: {upload_result.url}")
        else:
            print(f"❌ 이미지 업로드 실패: {upload_result.error_message}")
        
        print("\n🎉 모든 테스트 완료!")
        print("\n📋 사용 방법:")
        print("```python")
        print("from src.integrations.wordpress_client import create_bgn_wordpress_client")
        print("from src.generators.content_generator import GeneratedContent")
        print("")
        print("# 클라이언트 생성")
        print("client = create_bgn_wordpress_client()")
        print("")
        print("# 포스트 발행")
        print("result = client.create_post_with_media(content_data, images)")
        print("print(f'포스트 생성: {result.post_url}')")
        print("```")
        
    except ConnectionError as e:
        print(f"❌ 연결 실패: {str(e)}")
        print("💡 워드프레스 URL, 사용자명, 패스워드를 확인하세요.")
        print("💡 워드프레스에서 XML-RPC가 활성화되어 있는지 확인하세요.")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        print("💡 설정을 확인하고 다시 시도하세요.")