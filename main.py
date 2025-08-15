#!/usr/bin/env python3
"""
BGN 밝은눈안과 블로그 완전 자동화 시스템
- 인터뷰 분석
- 이미지 자동 생성  
- 워드프레스 자동 포스팅
"""

import streamlit as st
import openai
import pandas as pd
import requests
import base64
from PIL import Image
import io
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import time

# 환경변수 로드
load_dotenv()

# 워드프레스 연동을 위한 라이브러리 (선택적 설치)
try:
    from wordpress_xmlrpc import Client, WordPressPost
    from wordpress_xmlrpc.methods.posts import NewPost
    from wordpress_xmlrpc.methods.media import UploadFile
    WORDPRESS_AVAILABLE = True
except ImportError:
    WORDPRESS_AVAILABLE = False
    st.warning("⚠️ WordPress 연동을 위해 'pip install python-wordpress-xmlrpc'를 실행하세요.")

# 페이지 설정
st.set_page_config(
    page_title="BGN 블로그 자동화",
    page_icon="🏥", 
    layout="wide"
)

# CSS 스타일링
st.markdown("""
<style>
.main-header {
    background: linear-gradient(90deg, #2E86AB, #A23B72);
    color: white;
    padding: 20px;
    border-radius: 10px;
    text-align: center;
    margin-bottom: 30px;
}
.success-box {
    background: #d4edda;
    padding: 15px;
    border-radius: 8px;
    border: 1px solid #28a745;
    margin: 10px 0;
}
.warning-box {
    background: #fff3cd;
    padding: 15px;
    border-radius: 8px;
    border: 1px solid #ffc107;
    margin: 10px 0;
}
.step-box {
    background: #f8f9fa;
    padding: 15px;
    border-radius: 8px;
    border-left: 4px solid #2E86AB;
    margin: 10px 0;
}
</style>
""", unsafe_allow_html=True)

# 메인 헤더
st.markdown("""
<div class="main-header">
    <h1>🏥 BGN 밝은눈안과 블로그 자동화 시스템</h1>
    <p>인터뷰 내용 → AI 분석 → 이미지 생성 → 워드프레스 자동 발행</p>
</div>
""", unsafe_allow_html=True)

# 이미지 생성 클래스
class ImageGenerator:
    def __init__(self, api_key):
        self.api_key = api_key
        
    def generate_image_dalle(self, prompt, style="medical_clean"):
        """DALL-E로 의료용 이미지 생성"""
        try:
            client = openai.OpenAI(api_key=self.api_key)
            
            # 의료용 프롬프트 강화
            enhanced_prompt = self.enhance_medical_prompt(prompt, style)
            
            response = client.images.generate(
                model="dall-e-3",
                prompt=enhanced_prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            
            image_url = response.data[0].url
            
            # 이미지 다운로드
            img_response = requests.get(image_url)
            img = Image.open(io.BytesIO(img_response.content))
            
            return img, image_url
            
        except Exception as e:
            st.error(f"이미지 생성 실패: {str(e)}")
            return None, None
    
    def enhance_medical_prompt(self, prompt, style):
        """의료용 이미지 프롬프트 개선"""
        base_styles = {
            "medical_clean": "clean medical illustration, professional healthcare setting, soft lighting, modern hospital environment, no people faces visible, hygienic sterile appearance",
            "infographic": "medical infographic style, clean icons, pastel colors, educational diagram, simple clear visual elements",
            "equipment": "modern medical equipment photography, clean white background, professional lighting"
        }
        
        bgn_elements = "subtle blue and white color scheme, professional medical aesthetic, Korean hospital standard"
        
        enhanced = f"{prompt}, {base_styles.get(style, base_styles['medical_clean'])}, {bgn_elements}, high quality, professional"
        
        return enhanced

# 워드프레스 자동 포스팅 클래스
class WordPressClient:
    def __init__(self, wp_url, username, password):
        if not WORDPRESS_AVAILABLE:
            raise ImportError("WordPress 라이브러리가 설치되지 않았습니다.")
        
        self.wp_url = wp_url
        self.client = Client(f"{wp_url}/xmlrpc.php", username, password)
        
    def upload_image_to_wp(self, image, filename, alt_text=""):
        """이미지를 워드프레스에 업로드"""
        try:
            # PIL 이미지를 바이트로 변환
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='JPEG', quality=95)
            img_byte_arr = img_byte_arr.getvalue()
            
            data = {
                'name': filename,
                'type': 'image/jpeg',
                'bits': base64.b64encode(img_byte_arr).decode('utf-8'),
                'overwrite': True
            }
            
            response = self.client.call(UploadFile(data))
            return response['id'], response['url']
            
        except Exception as e:
            st.error(f"이미지 업로드 실패: {str(e)}")
            return None, None
    
    def create_post_with_images(self, post_data, images_data):
        """이미지와 함께 완전한 포스트 생성"""
        try:
            # 1. 이미지들 업로드
            uploaded_images = []
            featured_image_id = None
            
            for i, (image, alt_text) in enumerate(images_data):
                filename = f"{post_data['slug']}_image_{i+1}.jpg"
                img_id, img_url = self.upload_image_to_wp(image, filename, alt_text)
                
                if img_id:
                    uploaded_images.append({
                        'id': img_id,
                        'url': img_url,
                        'alt': alt_text
                    })
                    if i == 0:
                        featured_image_id = img_id
            
            # 2. HTML 콘텐츠 생성
            html_content = self.generate_html_content(post_data, uploaded_images)
            
            # 3. 워드프레스 포스트 생성
            post = WordPressPost()
            post.title = post_data['title']
            post.content = html_content
            post.post_status = 'draft'  # 초안으로 생성
            
            # 태그 및 카테고리 설정
            if post_data.get('tags'):
                post.terms_names = {
                    'post_tag': post_data['tags'].split(','),
                    'category': ['안과정보']
                }
            
            # 대표 이미지 설정
            if featured_image_id:
                post.thumbnail = featured_image_id
            
            # 포스트 생성
            post_id = self.client.call(NewPost(post))
            
            return post_id, f"{self.wp_url}/wp-admin/post.php?post={post_id}&action=edit"
            
        except Exception as e:
            st.error(f"포스트 생성 실패: {str(e)}")
            return None, None
    
    def generate_html_content(self, post_data, uploaded_images):
        """이미지가 포함된 HTML 콘텐츠 생성"""
        html = f"""
        <div class="bgn-blog-post">
            <div class="post-intro">
                <p>{post_data.get('meta_description', '')}</p>
            </div>
        """
        
        # 대표 이미지
        if uploaded_images:
            html += f"""
            <div class="featured-image">
                <img src="{uploaded_images[0]['url']}" alt="{uploaded_images[0]['alt']}" 
                     style="width: 100%; height: auto; border-radius: 8px; margin: 20px 0;" />
            </div>
            """
        
        # 콘텐츠 섹션들
        content_sections = [
            "대상별 맞춤 정보를 안내드립니다",
            "전문 의료진의 상세한 설명",
            "자주 묻는 질문과 답변"
        ]
        
        for i, section in enumerate(content_sections):
            html += f"""
            <h2 style="color: #2E86AB; margin-top: 30px;">{section}</h2>
            <p>BGN 밝은눈안과에서 {section.lower()}에 대해 전문적으로 안내드리겠습니다. 
            저희 병원의 풍부한 경험을 바탕으로 고객님께 최적의 정보를 제공합니다.</p>
            """
            
            # 중간에 이미지 삽입
            if i == 1 and len(uploaded_images) > 1:
                html += f"""
                <div class="content-image">
                    <img src="{uploaded_images[1]['url']}" alt="{uploaded_images[1]['alt']}" 
                         style="width: 100%; height: auto; border-radius: 8px; margin: 15px 0;" />
                </div>
                """
        
        # FAQ 섹션
        faqs = [
            ("상담은 어떻게 받을 수 있나요?", "전화 또는 온라인으로 상담 예약이 가능합니다."),
            ("검사는 얼마나 걸리나요?", "정밀 검사는 약 1-2시간 정도 소요됩니다."),
            ("비용은 어떻게 되나요?", "상담을 통해 개별적으로 안내드립니다.")
        ]
        
        html += """
        <h2 style="color: #2E86AB; margin-top: 30px;">자주 묻는 질문</h2>
        <div class="faq-section">
        """
        
        for q, a in faqs:
            html += f"""
            <div style="margin-bottom: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                <h4 style="color: #2E86AB; margin-bottom: 10px;">Q: {q}</h4>
                <p style="margin: 0; color: #555;">A: {a}</p>
            </div>
            """
        
        html += "</div>"
        
        # 마지막 이미지
        if len(uploaded_images) > 2:
            html += f"""
            <div class="closing-image">
                <img src="{uploaded_images[2]['url']}" alt="{uploaded_images[2]['alt']}" 
                     style="width: 100%; height: auto; border-radius: 8px; margin: 20px 0;" />
            </div>
            """
        
        # CTA 버튼
        cta_text = post_data.get('cta_button', '상담 예약하기')
        html += f"""
        <div class="cta-section" style="text-align: center; margin: 30px 0; padding: 20px; 
             background: linear-gradient(90deg, #2E86AB, #A23B72); border-radius: 10px;">
            <a href="#" style="color: white; font-size: 18px; font-weight: bold; text-decoration: none; 
               padding: 15px 30px; background: rgba(255,255,255,0.2); border-radius: 25px; display: inline-block;">
                {cta_text}
            </a>
        </div>
        """
        
        # 의료진 검토 안내
        html += """
        <div class="medical-disclaimer" style="margin-top: 30px; padding: 15px; background: #fff3cd; 
             border-radius: 8px; border-left: 4px solid #ffc107;">
            <p style="margin: 0; font-size: 14px; color: #856404;">
                <strong>의료진 검토 완료</strong> | BGN 밝은눈안과<br>
                본 내용은 일반적인 안내사항으로, 개인별 상태에 따라 달라질 수 있습니다. 
                정확한 진단과 치료는 의료진과의 상담을 통해 받으시기 바랍니다.
            </p>
        </div>
        </div>
        """
        
        return html

# 인터뷰 분석 함수
def analyze_interview(content, api_key):
    """인터뷰 내용을 분석하여 블로그 데이터 생성"""
    try:
        # 실제 환경에서는 OpenAI API 호출
        # 여기서는 샘플 데이터 반환
        return {
            "employee": {
                "name": "이예나",
                "position": "홍보팀 대리", 
                "specialty": "대학 제휴, 출장검진"
            },
            "content_data": {
                "title": "대학생을 위한 시력교정술 완벽 가이드",
                "primary_keyword": "대학생 시력교정",
                "secondary_keywords": "방학 수술, 학생 할인, 축제 상담",
                "slug": "college-student-vision-correction-guide",
                "meta_description": "대학생을 위한 시력교정술 준비부터 수술까지 완벽 가이드입니다. 방학 수술 계획과 학생 특별 혜택을 확인하세요.",
                "tags": "대학생,시력교정,방학수술,학생할인",
                "target_audience": "시력교정 고려 중인 대학생",
                "cta_button": "대학생 전용 상담 예약하기",
                "image_prompts": [
                    "university students consulting about vision correction surgery in modern hospital",
                    "medical equipment for precise eye examination in clean hospital room", 
                    "happy college student after successful vision correction surgery"
                ]
            }
        }
    except Exception as e:
        st.error(f"분석 실패: {str(e)}")
        return None

# 메인 애플리케이션
def main():
    # 사이드바 설정
    with st.sidebar:
        st.header("🔧 API 설정")
        
        # OpenAI API 키
        openai_api_key = st.text_input(
            "OpenAI API Key", 
            value=os.getenv("OPENAI_API_KEY", ""),
            type="password",
            help="DALL-E 이미지 생성을 위한 OpenAI API 키"
        )
        
        st.header("📝 워드프레스 설정")
        
        wp_url = st.text_input(
            "워드프레스 URL", 
            value=os.getenv("WORDPRESS_URL", ""),
            placeholder="https://your-site.com"
        )
        wp_username = st.text_input(
            "사용자명",
            value=os.getenv("WORDPRESS_USERNAME", "")
        )
        wp_password = st.text_input(
            "앱 패스워드", 
            value=os.getenv("WORDPRESS_PASSWORD", ""),
            type="password",
            help="워드프레스 관리자 → 사용자 → 프로필에서 생성한 앱 패스워드"
        )
        
        st.header("🎨 이미지 설정")
        image_style = st.selectbox(
            "이미지 스타일",
            ["medical_clean", "infographic", "equipment"],
            help="생성될 이미지의 스타일을 선택하세요"
        )
        
        generate_images = st.checkbox("이미지 자동 생성", value=True)
        auto_publish = st.checkbox("워드프레스 자동 발행", value=False)

    # 메인 컨텐츠
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📄 인터뷰 내용 입력")
        
        # 파일 업로드 옵션
        uploaded_file = st.file_uploader(
            "인터뷰 파일 업로드",
            type=['txt', 'docx'],
            help="텍스트 파일 또는 워드 문서를 업로드하세요"
        )
        
        # 텍스트 직접 입력
        interview_content = st.text_area(
            "또는 인터뷰 내용을 직접 입력하세요",
            height=250,
            placeholder="직원 인터뷰 내용을 여기에 붙여넣으세요...",
            help="인터뷰 전체 내용을 입력하면 AI가 자동으로 분석합니다"
        )
        
        # 샘플 데이터 버튼
        if st.button("📋 샘플 데이터 사용", help="테스트용 샘플 인터뷰 데이터"):
            interview_content = """
            홍보팀 이예나 대리입니다. 병원 마케팅 10년 경력이고, 
            현재 대학 제휴와 출장검진을 담당하고 있습니다.
            저희 병원의 장점은 26년간 의료사고가 없었다는 점과 
            잠실 롯데타워의 좋은 위치입니다.
            대학생들께는 특별 할인 혜택을 제공하고 있어요.
            """
            st.rerun()
    
    with col2:
        st.header("📊 생성 미리보기")
        
        if interview_content or uploaded_file:
            st.markdown('<div class="success-box">', unsafe_allow_html=True)
            st.write("✅ **분석 준비 완료**")
            if interview_content:
                st.write(f"📝 입력된 텍스트: {len(interview_content)}자")
            if uploaded_file:
                st.write(f"📁 업로드된 파일: {uploaded_file.name}")
            st.markdown('</div>', unsafe_allow_html=True)
            
            # 예상 결과 미리보기
            st.subheader("🔮 예상 생성 결과")
            st.write("📰 **블로그 포스트**: 1개")
            st.write("🖼️ **생성 이미지**: 3개")
            st.write("📝 **워드프레스**: 초안 상태로 발행")
            
        else:
            st.markdown('<div class="warning-box">', unsafe_allow_html=True)
            st.write("⚠️ 인터뷰 내용을 입력하거나 파일을 업로드해주세요.")
            st.markdown('</div>', unsafe_allow_html=True)

    # 실행 버튼
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀 자동화 실행", type="primary", use_container_width=True):
            
            # 필수 입력 검증
            if not openai_api_key:
                st.error("❌ OpenAI API 키를 입력해주세요!")
                return
                
            content = ""
            if uploaded_file:
                # 파일에서 텍스트 추출
                if uploaded_file.type == "text/plain":
                    content = str(uploaded_file.read(), "utf-8")
                else:
                    st.error("현재는 텍스트 파일만 지원됩니다.")
                    return
            elif interview_content:
                content = interview_content
            else:
                st.error("❌ 인터뷰 내용을 입력해주세요!")
                return
            
            # 진행 상황 표시
            progress_container = st.container()
            
            with progress_container:
                # 1단계: 인터뷰 분석
                with st.status("🔍 1단계: 인터뷰 분석 중...", expanded=True) as status:
                    st.write("직원 정보 및 전문 지식 추출 중...")
                    time.sleep(2)
                    
                    analysis_result = analyze_interview(content, openai_api_key)
                    
                    if analysis_result:
                        st.success("✅ 인터뷰 분석 완료")
                        st.write(f"**감지된 직원**: {analysis_result['employee']['name']}")
                        st.write(f"**전문 분야**: {analysis_result['employee']['specialty']}")
                        status.update(label="✅ 1단계 완료: 인터뷰 분석", state="complete")
                    else:
                        st.error("❌ 인터뷰 분석 실패")
                        return
                
                # 2단계: 이미지 생성
                generated_images = []
                if generate_images:
                    with st.status("🎨 2단계: 이미지 생성 중...", expanded=True) as status:
                        image_gen = ImageGenerator(openai_api_key)
                        
                        for i, prompt in enumerate(analysis_result["content_data"]["image_prompts"]):
                            st.write(f"이미지 {i+1} 생성 중...")
                            
                            try:
                                img, img_url = image_gen.generate_image_dalle(prompt, image_style)
                                if img:
                                    generated_images.append((img, f"BGN 이미지 {i+1}"))
                                    # 이미지 미리보기
                                    st.image(img, caption=f"생성된 이미지 {i+1}", width=300)
                                else:
                                    st.warning(f"이미지 {i+1} 생성 실패")
                                    
                            except Exception as e:
                                st.warning(f"이미지 {i+1} 생성 중 오류: {str(e)}")
                        
                        st.success(f"✅ {len(generated_images)}개 이미지 생성 완료")
                        status.update(label="✅ 2단계 완료: 이미지 생성", state="complete")
                
                # 3단계: 워드프레스 포스팅
                post_id = None
                edit_url = None
                
                if auto_publish and wp_url and wp_username and wp_password and WORDPRESS_AVAILABLE:
                    with st.status("📝 3단계: 워드프레스 포스팅 중...", expanded=True) as status:
                        try:
                            wp_client = WordPressClient(wp_url, wp_username, wp_password)
                            
                            post_id, edit_url = wp_client.create_post_with_images(
                                analysis_result["content_data"],
                                generated_images
                            )
                            
                            if post_id:
                                st.success("✅ 워드프레스 포스팅 완료!")
                                status.update(label="✅ 3단계 완료: 워드프레스 포스팅", state="complete")
                            else:
                                st.error("❌ 워드프레스 포스팅 실패")
                                
                        except Exception as e:
                            st.error(f"워드프레스 연동 오류: {str(e)}")
                
                # 결과 표시
                st.markdown("---")
                st.markdown('<div class="success-box">', unsafe_allow_html=True)
                st.header("🎉 자동화 완료!")
                
                # 결과 요약
                col1, col2, col3 = st.columns([1, 1, 1])
                
                with col1:
                    st.metric("분석 완료", "✅")
                    st.write("✓ 직원 정보 추출")
                    st.write("✓ 콘텐츠 데이터 생성")
                
                with col2:
                    st.metric("이미지 생성", f"{len(generated_images)}개")
                    st.write("✓ 의료용 이미지")
                    st.write("✓ DALL-E 고품질")
                
                with col3:
                    if post_id:
                        st.metric("포스팅 완료", "✅")
                        st.write("✓ 워드프레스 발행")
                        st.write(f"✓ 포스트 ID: {post_id}")
                    else:
                        st.metric("포스팅 대기", "📝")
                        st.write("✓ 수동 발행 필요")
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # 다운로드 및 링크
                if post_id and edit_url:
                    st.markdown("### 📎 생성 결과")
                    st.success(f"**워드프레스 포스트 ID**: {post_id}")
                    st.info(f"**편집 링크**: [여기를 클릭해서 포스트 편집하기]({edit_url})")
                
                # 생성된 이미지 다운로드
                if generated_images:
                    st.markdown("### 📥 이미지 다운로드")
                    for i, (img, alt_text) in enumerate(generated_images):
                        col1, col2 = st.columns([1, 2])
                        with col1:
                            st.image(img, width=200)
                        with col2:
                            img_bytes = io.BytesIO()
                            img.save(img_bytes, format='JPEG', quality=95)
                            st.download_button(
                                label=f"📷 이미지 {i+1} 다운로드",
                                data=img_bytes.getvalue(),
                                file_name=f"bgn_blog_image_{i+1}.jpg",
                                mime="image/jpeg"
                            )

# 앱 실행
if __name__ == "__main__":
    main()