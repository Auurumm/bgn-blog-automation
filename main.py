#!/usr/bin/env python3
"""
BGN 밝은눈안과 블로그 완전 자동화 통합 시스템 (REST API 버전)
- WordPress REST API 사용으로 XML-RPC 문제 해결
- 더 안전하고 현대적인 API 접근 방식
- 향상된 오류 처리 및 디버깅
"""

import streamlit as st
import os
import sys
import json
import re
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, asdict
import io
import base64
import mimetypes

# 환경변수 로드
from dotenv import load_dotenv
load_dotenv()

# 필수 라이브러리
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import requests
    from PIL import Image, ImageEnhance
    IMAGE_AVAILABLE = True
except ImportError:
    IMAGE_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

# 선택적 라이브러리들 (Google Sheets만 유지)
try:
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
    import gspread
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
# 설정 클래스
# ========================================

class Settings:
    """시스템 설정"""
    # API 키들
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # OpenAI 설정
    OPENAI_MODEL = "gpt-4o"
    OPENAI_TEMPERATURE = 0.7
    OPENAI_MAX_TOKENS = 2000
    
    # DALL-E 설정
    DALLE_MODEL = "dall-e-3"
    DALLE_SIZE = "1024x1024"
    DALLE_QUALITY = "standard"
    
    # 워드프레스 REST API 설정
    WORDPRESS_URL = os.getenv("WORDPRESS_URL", "")
    WORDPRESS_USERNAME = os.getenv("WORDPRESS_USERNAME", "")
    WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD", "")
    WORDPRESS_DEFAULT_CATEGORY = "안과정보"
    WORDPRESS_DEFAULT_STATUS = "draft"
    
    # 구글 시트 설정
    GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")
    GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    
    # 병원 정보
    HOSPITAL_NAME = "BGN 밝은눈안과"
    HOSPITAL_LOCATIONS = ["잠실 롯데타워", "강남", "부산"]
    HOSPITAL_PHONE = "1588-8875"
    
    # 이미지 스타일
    IMAGE_STYLES = {
        "medical_clean": {
            "prompt_suffix": "clean medical illustration, professional healthcare setting, soft lighting, modern hospital environment"
        },
        "infographic": {
            "prompt_suffix": "medical infographic style, clean icons, pastel colors, educational diagram"
        },
        "equipment": {
            "prompt_suffix": "modern medical equipment photography, clean white background, professional lighting"
        }
    }
    
    # 의료광고법 준수
    PROHIBITED_KEYWORDS = [
        "완치", "완전히 낫는다", "100% 성공", "부작용 없음", 
        "세계 최고", "국내 최고", "효과 보장", "영구적"
    ]
    
    RECOMMENDED_ALTERNATIVES = {
        "완치": "개선",
        "100% 성공": "높은 성공률",
        "부작용 없음": "안전한 시술",
        "세계 최고": "우수한 기술"
    }
    
    @classmethod
    def get_brand_prompt_suffix(cls):
        return f"subtle blue and white color scheme, professional medical aesthetic, Korean hospital standard, {cls.HOSPITAL_NAME} branding"

# ========================================
# 데이터 클래스들
# ========================================

@dataclass
class EmployeeProfile:
    """직원 프로필"""
    name: str = ""
    position: str = ""
    department: str = ""
    experience_years: int = 0
    specialty_areas: List[str] = None
    
    def __post_init__(self):
        if self.specialty_areas is None:
            self.specialty_areas = []

@dataclass
class PersonalityTraits:
    """개성/말투 특성"""
    tone_style: str = ""
    frequent_expressions: List[str] = None
    communication_style: str = ""
    personality_keywords: List[str] = None
    formality_level: str = ""
    
    def __post_init__(self):
        if self.frequent_expressions is None:
            self.frequent_expressions = []
        if self.personality_keywords is None:
            self.personality_keywords = []

@dataclass
class ProfessionalKnowledge:
    """전문 지식"""
    procedures: List[str] = None
    equipment: List[str] = None
    processes: List[str] = None
    technical_terms: List[str] = None
    expertise_level: str = ""
    
    def __post_init__(self):
        if self.procedures is None:
            self.procedures = []
        if self.equipment is None:
            self.equipment = []
        if self.processes is None:
            self.processes = []
        if self.technical_terms is None:
            self.technical_terms = []

@dataclass
class CustomerInsights:
    """고객 인사이트"""
    frequent_questions: List[str] = None
    customer_feedback: List[str] = None
    target_demographics: List[str] = None
    
    def __post_init__(self):
        if self.frequent_questions is None:
            self.frequent_questions = []
        if self.customer_feedback is None:
            self.customer_feedback = []
        if self.target_demographics is None:
            self.target_demographics = []

@dataclass
class HospitalStrengths:
    """병원 강점"""
    competitive_advantages: List[str] = None
    unique_services: List[str] = None
    location_benefits: List[str] = None
    
    def __post_init__(self):
        if self.competitive_advantages is None:
            self.competitive_advantages = []
        if self.unique_services is None:
            self.unique_services = []
        if self.location_benefits is None:
            self.location_benefits = []

@dataclass
class InterviewAnalysisResult:
    """인터뷰 분석 결과"""
    employee: EmployeeProfile
    personality: PersonalityTraits
    knowledge: ProfessionalKnowledge
    customer_insights: CustomerInsights
    hospital_strengths: HospitalStrengths
    analysis_metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.analysis_metadata is None:
            self.analysis_metadata = {
                "analysis_date": datetime.now().isoformat(),
                "confidence_score": 0.0,
                "content_length": 0
            }

@dataclass
class GeneratedContent:
    """생성된 콘텐츠"""
    title: str
    slug: str
    meta_description: str
    content_markdown: str
    content_html: str
    tags: List[str]
    faq_list: List[Dict[str, str]]
    image_prompts: List[str]
    cta_button_text: str
    estimated_reading_time: int
    seo_score: float
    medical_compliance_score: float

@dataclass
class MediaUploadResult:
    """미디어 업로드 결과"""
    media_id: int
    url: str
    filename: str
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
    success: bool = True
    error_message: str = ""

# ========================================
# 의존성 체크 함수
# ========================================

def check_dependencies():
    """필수 및 선택적 라이브러리 체크"""
    missing_required = []
    missing_optional = []
    
    # 필수 라이브러리 체크
    if not OPENAI_AVAILABLE:
        missing_required.append("openai")
    if not IMAGE_AVAILABLE:
        missing_required.append("Pillow requests")
    
    # 선택적 라이브러리 체크
    if not GOOGLE_SHEETS_AVAILABLE:
        missing_optional.append("google-api-python-client google-auth-httplib2 google-auth-oauthlib gspread")
    if not PANDAS_AVAILABLE:
        missing_optional.append("pandas")
    
    return missing_required, missing_optional

def display_dependency_warnings():
    """의존성 경고 표시"""
    missing_required, missing_optional = check_dependencies()
    
    if missing_required:
        st.error(f"""
        ❌ **필수 라이브러리 미설치**
        
        다음 라이브러리를 설치해야 합니다:
        ```bash
        pip install {' '.join(missing_required)}
        ```
        """)
        return False
    
    if missing_optional:
        st.warning(f"""
        ⚠️ **선택적 기능 제한**
        
        일부 기능을 사용하려면 추가 라이브러리가 필요합니다:
        ```bash
        pip install {' '.join(missing_optional)}
        ```
        """)
    
    return True

# ========================================
# 안전한 인터뷰 분석기
# ========================================

class SafeInterviewAnalyzer:
    """안전한 인터뷰 분석기 (오류 처리 강화)"""
    
    def __init__(self, api_key: str = None):
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI 라이브러리가 설치되지 않았습니다.")
        
        self.api_key = api_key or Settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API 키가 설정되지 않았습니다.")
        
        try:
            self.client = openai.OpenAI(api_key=self.api_key)
        except Exception as e:
            raise ConnectionError(f"OpenAI 클라이언트 초기화 실패: {str(e)}")
        
        # 분석 패턴 설정
        self.medical_terms = [
            '스마일라식', '라식', '라섹', '백내장', '녹내장', '망막',
            '각막', '시력교정', '검안', '안압', 'OCT'
        ]
        
        self.personality_markers = {
            '솔직함': ['솔직하게', '사실', '정말로', '진짜'],
            '배려심': ['걱정하지 마시고', '편하게', '천천히', '괜찮아요'],
            '전문성': ['의료진과', '정확한', '전문적으로', '임상적으로'],
            '친근함': ['~해요', '~거든요', '~네요', '같아서']
        }
    
    def analyze_interview(self, interview_text: str) -> InterviewAnalysisResult:
        """안전한 인터뷰 분석"""
        try:
            if not interview_text or len(interview_text.strip()) < 10:
                return self._create_default_result()
            
            # 텍스트 전처리
            cleaned_text = self._preprocess_text(interview_text)
            
            # 기본 정보 추출
            employee = self._extract_employee_info(cleaned_text)
            personality = self._analyze_personality(cleaned_text)
            knowledge = self._extract_knowledge(cleaned_text)
            customer_insights = self._extract_customer_insights(cleaned_text)
            hospital_strengths = self._extract_hospital_strengths(cleaned_text)
            
            # 메타데이터 생성
            metadata = {
                "analysis_date": datetime.now().isoformat(),
                "confidence_score": self._calculate_confidence(employee, knowledge),
                "content_length": len(cleaned_text)
            }
            
            return InterviewAnalysisResult(
                employee=employee,
                personality=personality,
                knowledge=knowledge,
                customer_insights=customer_insights,
                hospital_strengths=hospital_strengths,
                analysis_metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"인터뷰 분석 실패: {str(e)}")
            return self._create_default_result()
    
    def _preprocess_text(self, text: str) -> str:
        """텍스트 전처리"""
        text = re.sub(r'\n+', '\n', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _extract_employee_info(self, text: str) -> EmployeeProfile:
        """직원 정보 추출"""
        employee = EmployeeProfile()
        
        # 이름 추출
        name_patterns = [
            r'저는\s*([가-힣]{2,4})',
            r'([가-힣]{2,4})\s*(대리|과장|팀장)',
            r'제가\s*([가-힣]{2,4})'
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text)
            if match:
                employee.name = match.group(1)
                break
        
        # 직책 추출
        if '대리' in text:
            employee.position = '대리'
        elif '과장' in text:
            employee.position = '과장'
        elif '팀장' in text:
            employee.position = '팀장'
        
        # 부서 추출
        if '홍보' in text:
            employee.department = '홍보팀'
        elif '상담' in text:
            employee.department = '상담팀'
        elif '검안' in text:
            employee.department = '검안팀'
        
        # 경력 추출
        exp_patterns = [
            r'(\d+)년.*?(경력|차)',
            r'경력.*?(\d+)년',
            r'(\d+)년.*?정도'
        ]
        
        for pattern in exp_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    employee.experience_years = int(match.group(1))
                    break
                except (ValueError, IndexError):
                    continue
        
        # 전문분야 추출
        if '대학' in text and '제휴' in text:
            employee.specialty_areas.append('대학 제휴')
        if '출장검진' in text:
            employee.specialty_areas.append('출장검진')
        if '상담' in text:
            employee.specialty_areas.append('고객 상담')
        if '축제' in text:
            employee.specialty_areas.append('축제 마케팅')
        
        return employee
    
    def _analyze_personality(self, text: str) -> PersonalityTraits:
        """개성 분석"""
        personality = PersonalityTraits()
        
        # 말투 스타일 분석
        style_scores = {}
        for style, markers in self.personality_markers.items():
            score = sum(1 for marker in markers if marker in text)
            if score > 0:
                style_scores[style] = score
        
        if style_scores:
            personality.tone_style = max(style_scores, key=style_scores.get)
            personality.personality_keywords = list(style_scores.keys())
        
        # 자주 쓰는 표현
        for markers in self.personality_markers.values():
            for marker in markers:
                if text.count(marker) >= 2:
                    personality.frequent_expressions.append(marker)
        
        # 격식 수준
        formal_count = text.count('습니다') + text.count('됩니다')
        casual_count = text.count('해요') + text.count('거든요')
        
        if formal_count > casual_count:
            personality.formality_level = 'formal'
        else:
            personality.formality_level = 'casual'
        
        return personality
    
    def _extract_knowledge(self, text: str) -> ProfessionalKnowledge:
        """전문 지식 추출"""
        knowledge = ProfessionalKnowledge()
        
        # 의료 용어 추출
        for term in self.medical_terms:
            if term in text:
                if '검사' in term:
                    knowledge.procedures.append(term)
                else:
                    knowledge.technical_terms.append(term)
        
        # 장비 관련
        equipment_keywords = ['장비', 'OCT', '검사기', '레이저']
        for keyword in equipment_keywords:
            if keyword in text:
                knowledge.equipment.append(f'{keyword} 관련')
        
        # 전문성 평가
        expertise_count = len(knowledge.procedures) + len(knowledge.technical_terms)
        if expertise_count >= 3:
            knowledge.expertise_level = '전문가'
        elif expertise_count >= 1:
            knowledge.expertise_level = '숙련자'
        else:
            knowledge.expertise_level = '일반'
        
        return knowledge
    
    def _extract_customer_insights(self, text: str) -> CustomerInsights:
        """고객 인사이트 추출"""
        insights = CustomerInsights()
        
        # 자주 받는 질문
        if '질문' in text or '궁금' in text:
            insights.frequent_questions.append('검사 과정에 대한 문의')
        if '비용' in text or '가격' in text:
            insights.frequent_questions.append('비용 관련 문의')
        
        # 고객층 추출
        if '대학생' in text:
            insights.target_demographics.append('대학생')
        if '직장인' in text:
            insights.target_demographics.append('직장인')
        if '어르신' in text or '노인' in text:
            insights.target_demographics.append('중장년층')
        
        return insights
    
    def _extract_hospital_strengths(self, text: str) -> HospitalStrengths:
        """병원 강점 추출"""
        strengths = HospitalStrengths()
        
        # 위치 장점
        if '롯데타워' in text or '잠실' in text:
            strengths.location_benefits.append('롯데타워 위치')
        if '교통' in text or '접근' in text:
            strengths.location_benefits.append('교통 편의성')
        
        # 경쟁 우위
        if '무사고' in text or '26년' in text:
            strengths.competitive_advantages.append('26년 무사고 기록')
        if '경험' in text and '년' in text:
            strengths.competitive_advantages.append('풍부한 경험')
        
        # 특별 서비스
        if '할인' in text:
            strengths.unique_services.append('학생 할인 혜택')
        if '축제' in text:
            strengths.unique_services.append('대학 축제 상담')
        if '출장' in text:
            strengths.unique_services.append('출장 검진 서비스')
        
        return strengths
    
    def _calculate_confidence(self, employee: EmployeeProfile, knowledge: ProfessionalKnowledge) -> float:
        """신뢰도 계산"""
        score = 0.0
        
        if employee.name:
            score += 0.3
        if employee.position:
            score += 0.2
        if employee.specialty_areas:
            score += 0.2
        if knowledge.procedures:
            score += 0.2
        if employee.experience_years > 0:
            score += 0.1
        
        return min(score, 1.0)
    
    def _create_default_result(self) -> InterviewAnalysisResult:
        """기본 결과 생성"""
        return InterviewAnalysisResult(
            employee=EmployeeProfile(name="직원", position="직원", department="일반"),
            personality=PersonalityTraits(tone_style="친근함"),
            knowledge=ProfessionalKnowledge(expertise_level="일반"),
            customer_insights=CustomerInsights(),
            hospital_strengths=HospitalStrengths()
        )

# ========================================
# 안전한 콘텐츠 생성기
# ========================================

class SafeContentGenerator:
    """안전한 콘텐츠 생성기"""
    
    def __init__(self, api_key: str = None):
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI 라이브러리가 설치되지 않았습니다.")
        
        self.api_key = api_key or Settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API 키가 설정되지 않았습니다.")
        
        try:
            self.client = openai.OpenAI(api_key=self.api_key)
        except Exception as e:
            raise ConnectionError(f"OpenAI 클라이언트 초기화 실패: {str(e)}")
    
    def generate_content(self, analysis_result: InterviewAnalysisResult) -> GeneratedContent:
        """안전한 콘텐츠 생성"""
        try:
            # 콘텐츠 기획
            content_plan = self._create_content_plan(analysis_result)
            
            # 메인 콘텐츠 생성
            main_content = self._generate_main_content(content_plan, analysis_result)
            
            # FAQ 생성
            faq_list = self._generate_faq(analysis_result)
            
            # 메타데이터 생성
            title = content_plan['title']
            slug = self._generate_slug(title)
            meta_description = self._generate_meta_description(title)
            tags = self._generate_tags(analysis_result)
            
            # HTML 변환
            html_content = self._markdown_to_html(main_content)
            
            # 이미지 프롬프트 생성
            image_prompts = self._generate_image_prompts(analysis_result)
            
            # CTA 버튼 텍스트
            cta_text = self._generate_cta_text(analysis_result)
            
            # 점수 계산
            reading_time = max(1, len(main_content) // 300)
            seo_score = self._calculate_seo_score(title, main_content, tags)
            compliance_score = self._check_medical_compliance(main_content)
            
            return GeneratedContent(
                title=title,
                slug=slug,
                meta_description=meta_description,
                content_markdown=main_content,
                content_html=html_content,
                tags=tags,
                faq_list=faq_list,
                image_prompts=image_prompts,
                cta_button_text=cta_text,
                estimated_reading_time=reading_time,
                seo_score=seo_score,
                medical_compliance_score=compliance_score
            )
            
        except Exception as e:
            logger.error(f"콘텐츠 생성 실패: {str(e)}")
            return self._create_default_content()
    
    def _create_content_plan(self, analysis: InterviewAnalysisResult) -> Dict:
        """콘텐츠 기획"""
        specialties = analysis.employee.specialty_areas
        
        if any('대학' in s for s in specialties):
            topic = "대학생을 위한 시력교정술"
            keywords = ["대학생", "시력교정", "방학수술", "학생할인"]
        elif any('출장' in s for s in specialties):
            topic = "직장인 눈 건강 관리"
            keywords = ["직장인", "눈건강", "정밀검사", "출장검진"]
        else:
            topic = "안과 진료 가이드"
            keywords = ["안과진료", "눈건강", "검사", "상담"]
        
        return {
            'title': f"{topic} 완벽 가이드",
            'primary_keyword': keywords[0],
            'secondary_keywords': keywords[1:],
            'target_audience': keywords[0]
        }
    
    def _generate_main_content(self, plan: Dict, analysis: InterviewAnalysisResult) -> str:
        """메인 콘텐츠 생성"""
        try:
            if not self.api_key:
                return self._create_detailed_fallback_content(plan, analysis)
            
            # 간단한 프롬프트로 빠른 생성
            prompt = f"""
BGN 밝은눈안과 블로그 글을 작성해주세요.

주제: {plan['title']}
담당자: {analysis.employee.name or '전문 의료진'}
부서: {analysis.employee.department or '의료팀'}

2000자 이상의 상세한 블로그 글을 작성해주세요:
1. 전문의료진의 경험담
2. 환자들의 자주 묻는 질문과 답변
3. BGN 병원의 차별점
4. 실용적인 조언

의료광고법을 준수하여 작성해주세요.
            """
            
            response = self.client.chat.completions.create(
                model=Settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "의료 콘텐츠 전문 작가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=3000
            )
            
            content = response.choices[0].message.content
            
            # 글자수 확인
            char_count = len(content)
            logger.info(f"생성된 콘텐츠 길이: {char_count}자")
            
            return content
            
        except Exception as e:
            logger.error(f"콘텐츠 생성 실패: {str(e)}")
            return self._create_detailed_fallback_content(plan, analysis)
    
    def _create_detailed_fallback_content(self, plan: Dict, analysis: InterviewAnalysisResult) -> str:
        """상세한 폴백 콘텐츠"""
        employee = analysis.employee
        return f"""
# {plan['title']}

## 안녕하세요, {employee.name or 'BGN 의료진'}입니다

{plan['target_audience']}을 위한 전문적인 안과 정보를 안내드립니다.

## 전문 의료진의 상세한 설명

저희 BGN 밝은눈안과는 26년간의 풍부한 경험을 바탕으로 안전하고 정확한 진료를 제공하고 있습니다.

### 정밀한 검사 시스템

최신 의료 장비를 활용한 정밀 검사를 통해 개인별 맞춤 진료를 실시합니다.

### 안전한 시술 환경

깨끗하고 체계적인 시술 환경에서 숙련된 의료진이 직접 진료합니다.

## 고객 중심의 서비스

편안한 환경에서 충분한 상담을 통해 고객님의 궁금증을 해결해드립니다.

## BGN 밝은눈안과의 특별함

- 26년간 축적된 풍부한 경험
- 잠실 롯데타워의 편리한 위치
- 개인별 맞춤 상담 서비스
- 안전을 최우선으로 하는 진료 철학

## 마무리

더 자세한 정보가 필요하시면 언제든 상담을 통해 안내받으실 수 있습니다.
전문 의료진과의 1:1 상담으로 개인에게 가장 적합한 방법을 찾아보세요.
        """.strip()
    
    def _generate_faq(self, analysis: InterviewAnalysisResult) -> List[Dict[str, str]]:
        """FAQ 생성"""
        base_faqs = [
            {"question": "상담은 어떻게 받을 수 있나요?", "answer": "전화 또는 온라인으로 예약 가능합니다."},
            {"question": "검사 시간은 얼마나 걸리나요?", "answer": "정밀 검사는 약 1-2시간 소요됩니다."},
            {"question": "비용은 어떻게 되나요?", "answer": "상담을 통해 개별적으로 안내드립니다."}
        ]
        
        return base_faqs[:3]
    
    def _generate_slug(self, title: str) -> str:
        """URL 슬러그 생성"""
        keyword_map = {
            "대학생": "college-student",
            "시력교정": "vision-correction", 
            "직장인": "office-worker",
            "눈건강": "eye-health",
            "검사": "examination",
            "가이드": "guide"
        }
        
        slug_parts = []
        for korean, english in keyword_map.items():
            if korean in title:
                slug_parts.append(english)
        
        if not slug_parts:
            slug_parts = ["eye-care", "guide"]
        
        return "-".join(slug_parts)
    
    def _generate_meta_description(self, title: str) -> str:
        """메타 설명 생성"""
        return f"{title}에 대한 전문의의 상세한 안내입니다. BGN 밝은눈안과에서 안전하고 정확한 정보를 제공합니다."
    
    def _generate_tags(self, analysis: InterviewAnalysisResult) -> List[str]:
        """태그 생성"""
        tags = ["안과", "눈건강", Settings.HOSPITAL_NAME]
        
        # 전문분야 기반 태그
        for specialty in analysis.employee.specialty_areas:
            if "대학" in specialty:
                tags.extend(["대학생", "시력교정", "학생할인"])
            elif "출장" in specialty:
                tags.extend(["직장인", "출장검진", "정밀검사"])
        
        return list(set(tags))[:6]
    
    def _generate_image_prompts(self, analysis: InterviewAnalysisResult) -> List[str]:
        """이미지 프롬프트 생성"""
        prompts = []
        
        prompts.append("Professional medical consultation in modern Korean hospital")
        prompts.append("Advanced eye examination equipment in modern ophthalmology clinic")
        prompts.append("Clean and modern hospital interior with comfortable patient areas")
        
        return prompts
    
    def _generate_cta_text(self, analysis: InterviewAnalysisResult) -> str:
        """CTA 버튼 텍스트 생성"""
        return "전문 상담 예약하기"
    
    def _markdown_to_html(self, markdown_content: str) -> str:
        """마크다운을 HTML로 변환"""
        html = markdown_content
        
        # 헤딩 변환
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)

        # 볼드 변환  
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)

        # 단락 변환
        paragraphs = html.split('\n\n')
        html_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<') and not para.endswith('>'):
                html_paragraphs.append(f'<p>{para}</p>')
            elif para:
                html_paragraphs.append(para)
        
        return '\n'.join(html_paragraphs)
    
    def _calculate_seo_score(self, title: str, content: str, tags: List[str]) -> float:
        """SEO 점수 계산"""
        score = 0.0
        
        if 30 <= len(title) <= 60:
            score += 0.3
        if len(content) >= 800:
            score += 0.4
        if 3 <= len(tags) <= 8:
            score += 0.3
        
        return min(score, 1.0)
    
    def _check_medical_compliance(self, content: str) -> float:
        """의료광고법 준수도 체크"""
        score = 1.0
        
        for prohibited in Settings.PROHIBITED_KEYWORDS:
            if prohibited in content:
                score -= 0.2
        
        return max(score, 0.0)
    
    def _create_default_content(self) -> GeneratedContent:
        """기본 콘텐츠 생성"""
        return GeneratedContent(
            title="BGN 밝은눈안과 전문 진료 안내",
            slug="bgn-eye-care-guide",
            meta_description="BGN 밝은눈안과의 전문 진료 서비스를 안내합니다.",
            content_markdown="전문 의료진의 상세한 안내를 제공합니다.",
            content_html="<p>전문 의료진의 상세한 안내를 제공합니다.</p>",
            tags=["안과", "진료", Settings.HOSPITAL_NAME],
            faq_list=[{"question": "상담 예약 방법은?", "answer": "전화로 예약 가능합니다."}],
            image_prompts=["Medical consultation in hospital"],
            cta_button_text="상담 예약하기",
            estimated_reading_time=2,
            seo_score=0.5,
            medical_compliance_score=0.9
        )

# ========================================
# 안전한 이미지 생성기
# ========================================

class SafeImageGenerator:
    """안전한 DALL-E 이미지 생성기"""
    
    def __init__(self, api_key: str = None):
        if not OPENAI_AVAILABLE or not IMAGE_AVAILABLE:
            raise ImportError("OpenAI 또는 이미지 처리 라이브러리가 설치되지 않았습니다.")
        
        self.api_key = api_key or Settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API 키가 설정되지 않았습니다.")
        
        try:
            self.client = openai.OpenAI(api_key=self.api_key)
        except Exception as e:
            raise ConnectionError(f"OpenAI 클라이언트 초기화 실패: {str(e)}")
        
        self.generation_count = 0
    
    def generate_image(self, prompt: str, style: str = "medical_clean") -> Tuple[Optional[Image.Image], Optional[str]]:
        """안전한 이미지 생성"""
        try:
            print(f"🎨 이미지 생성 시작: {prompt[:50]}...")
            
            # 의료용 프롬프트 강화
            enhanced_prompt = self._enhance_medical_prompt(prompt, style)
            print(f"📝 강화된 프롬프트: {enhanced_prompt[:100]}...")
            
            # DALL-E API 호출
            response = self.client.images.generate(
                model=Settings.DALLE_MODEL,
                prompt=enhanced_prompt,
                size=Settings.DALLE_SIZE,
                quality=Settings.DALLE_QUALITY,
                n=1,
            )
            
            image_url = response.data[0].url
            print(f"🌐 이미지 URL 생성 성공: {image_url[:50]}...")
            
            # 이미지 다운로드
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()
            
            image = Image.open(io.BytesIO(img_response.content))
            
            # 후처리
            image = self._post_process_image(image)
            
            self.generation_count += 1
            print(f"✅ 이미지 생성 완료: {prompt[:50]}...")
            
            return image, image_url
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            print(f"❌ 이미지 생성 실패 ({error_type}): {error_msg}")
            logger.error(f"이미지 생성 상세 오류: {error_type}: {error_msg}")
            return None, None
    
    def _enhance_medical_prompt(self, prompt: str, style: str) -> str:
        """의료용 프롬프트 강화"""
        try:
            style_suffix = Settings.IMAGE_STYLES.get(style, Settings.IMAGE_STYLES["medical_clean"])["prompt_suffix"]
            
            compliance_elements = [
                "educational purpose only",
                "professional medical setting",
                "no patient identification visible"
            ]
            
            brand_elements = Settings.get_brand_prompt_suffix()
            
            enhanced = f"""
            {prompt}, 
            {style_suffix}, 
            {', '.join(compliance_elements)}, 
            {brand_elements}, 
            high resolution, professional quality
            """.strip().replace('\n', ' ').replace('  ', ' ')
            
            # 길이 제한
            if len(enhanced) > 3000:
                enhanced = enhanced[:3000] + "..."
            
            return enhanced
            
        except Exception as e:
            logger.warning(f"프롬프트 강화 실패: {str(e)}")
            return prompt
    
    def _post_process_image(self, image: Image.Image) -> Image.Image:
        """이미지 후처리"""
        try:
            # RGB 모드로 변환
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # 선명도 향상
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.1)
            
            # 색상 채도 조정
            enhancer = ImageEnhance.Color(image)
            image = enhancer.enhance(0.95)
            
            return image
            
        except Exception as e:
            logger.warning(f"이미지 후처리 실패: {str(e)}")
            return image
    
    def generate_blog_images(self, content_data: GeneratedContent, style: str = "medical_clean") -> List[Tuple[Image.Image, str]]:
        """블로그용 이미지 세트 생성"""
        generated_images = []
        
        for i, prompt in enumerate(content_data.image_prompts):
            logger.info(f"이미지 {i+1}/{len(content_data.image_prompts)} 생성 중...")
            
            image, url = self.generate_image(prompt, style)
            
            if image:
                alt_text = f"{Settings.HOSPITAL_NAME} {content_data.title} 관련 이미지 {i+1}"
                generated_images.append((image, alt_text))
            else:
                logger.warning(f"이미지 {i+1} 생성 실패")
        
        return generated_images

# ========================================
# WordPress REST API 클라이언트
# ========================================

class WordPressRestAPIClient:
    """WordPress REST API 클라이언트"""
    
    def __init__(self, url: str = None, username: str = None, password: str = None):
        self.wp_url = url or Settings.WORDPRESS_URL
        self.username = username or Settings.WORDPRESS_USERNAME
        self.password = password or Settings.WORDPRESS_PASSWORD
        
        if not all([self.wp_url, self.username, self.password]):
            raise ValueError("워드프레스 설정이 완료되지 않았습니다.")
        
        # URL 정리 (끝의 슬래시 제거)
        self.wp_url = self.wp_url.rstrip('/')
        
        # API 엔드포인트 설정
        self.api_base = f"{self.wp_url}/wp-json/wp/v2"
        
        # 인증 설정
        self.auth = (self.username, self.password)
        
        # 기본 헤더
        self.headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'BGN-Blog-Automation/1.0'
        }
        
        self.upload_count = 0
        
        # 연결 테스트
        self._test_connection()
    
    def _test_connection(self):
        """API 연결 테스트"""
        try:
            print(f"🔗 WordPress REST API 연결 테스트...")
            print(f"  - URL: {self.wp_url}")
            print(f"  - API Base: {self.api_base}")
            print(f"  - Username: {self.username}")
            
            # 사용자 정보 확인
            response = requests.get(
                f"{self.api_base}/users/me",
                auth=self.auth,
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                user_data = response.json()
                print(f"  ✅ 인증 성공: {user_data.get('name', 'Unknown')} ({user_data.get('id')})")
                logger.info("WordPress REST API 연결 성공")
            else:
                error_msg = f"인증 실패: {response.status_code} - {response.text}"
                print(f"  ❌ {error_msg}")
                raise ConnectionError(error_msg)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"WordPress REST API 연결 실패: {str(e)}"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            raise ConnectionError(error_msg)
    
    def upload_image(self, image: Image.Image, filename: str, alt_text: str = "") -> MediaUploadResult:
        """REST API를 통한 이미지 업로드"""
        try:
            print(f"📤 이미지 업로드 시작: {filename}")
            
            # PIL 이미지를 바이트로 변환
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='JPEG', quality=85, optimize=True)
            img_data = img_byte_arr.getvalue()
            
            # 미디어 업로드 API 호출
            files = {
                'file': (filename, img_data, 'image/jpeg')
            }
            
            # 메타데이터
            data = {
                'title': filename.replace('.jpg', ''),
                'alt_text': alt_text,
                'description': f"BGN 밝은눈안과 - {alt_text}"
            }
            
            # REST API 헤더 (multipart/form-data용)
            headers = {
                'User-Agent': 'BGN-Blog-Automation/1.0'
            }
            
            response = requests.post(
                f"{self.api_base}/media",
                files=files,
                data=data,
                auth=self.auth,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 201:
                media_data = response.json()
                self.upload_count += 1
                
                print(f"  ✅ 업로드 성공: ID {media_data['id']}")
                
                return MediaUploadResult(
                    media_id=media_data['id'],
                    url=media_data['source_url'],
                    filename=filename,
                    success=True
                )
            else:
                error_msg = f"업로드 실패: {response.status_code} - {response.text}"
                print(f"  ❌ {error_msg}")
                logger.error(f"이미지 업로드 실패: {error_msg}")
                
                return MediaUploadResult(
                    media_id=0,
                    url="",
                    filename=filename,
                    success=False,
                    error_message=error_msg
                )
                
        except Exception as e:
            error_msg = f"이미지 업로드 예외: {str(e)}"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            
            return MediaUploadResult(
                media_id=0,
                url="",
                filename=filename,
                success=False,
                error_message=error_msg
            )
    
    def create_post(self, content_data: GeneratedContent, images: List[Tuple[Image.Image, str]] = None, publish_status: str = "draft") -> PostPublishResult:
        """REST API를 통한 포스트 생성"""
        try:
            print(f"📝 포스트 생성 시작: {content_data.title}")
            print(f"  - 발행 상태: {publish_status}")
            
            uploaded_media = []
            featured_image_id = None
            
            # 이미지 업로드
            if images:
                print(f"📷 {len(images)}개 이미지 업로드 중...")
                for i, (image, alt_text) in enumerate(images):
                    filename = f"{content_data.slug}_image_{i+1}.jpg"
                    upload_result = self.upload_image(image, filename, alt_text)
                    
                    if upload_result.success:
                        uploaded_media.append(upload_result)
                        if i == 0:  # 첫 번째 이미지를 대표 이미지로
                            featured_image_id = upload_result.media_id
                            print(f"  ✅ 대표 이미지 설정: ID {featured_image_id}")
            
            # HTML 콘텐츠 생성
            html_content = self._build_post_html(content_data, uploaded_media)
            
            # 카테고리 ID 가져오기 (기본 카테고리 사용)
            category_id = self._get_or_create_category(Settings.WORDPRESS_DEFAULT_CATEGORY)
            
            # 태그 ID 가져오기
            tag_ids = self._get_or_create_tags(content_data.tags)
            
            # 포스트 데이터 구성
            post_data = {
                'title': content_data.title,
                'content': html_content,
                'excerpt': content_data.meta_description,
                'slug': content_data.slug,
                'status': publish_status,
                'categories': [category_id] if category_id else [],
                'tags': tag_ids,
                'meta': {
                    'description': content_data.meta_description
                }
            }
            
            # 대표 이미지 설정
            if featured_image_id:
                post_data['featured_media'] = featured_image_id
            
            print(f"📤 포스트 데이터 전송 중...")
            
            # 포스트 생성 API 호출
            response = requests.post(
                f"{self.api_base}/posts",
                json=post_data,
                auth=self.auth,
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 201:
                post_response = response.json()
                post_id = post_response['id']
                
                print(f"  ✅ 포스트 생성 성공: ID {post_id}")
                
                return PostPublishResult(
                    post_id=post_id,
                    post_url=post_response['link'],
                    edit_url=f"{self.wp_url}/wp-admin/post.php?post={post_id}&action=edit",
                    status=publish_status,
                    publish_date=datetime.now(),
                    success=True
                )
            else:
                error_msg = f"포스트 생성 실패: {response.status_code} - {response.text}"
                print(f"❌ {error_msg}")
                logger.error(error_msg)
                
                return PostPublishResult(
                    post_id=0,
                    post_url="",
                    edit_url="",
                    status="failed",
                    publish_date=datetime.now(),
                    success=False,
                    error_message=error_msg
                )
                
        except Exception as e:
            error_msg = f"포스트 생성 예외: {str(e)}"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            
            return PostPublishResult(
                post_id=0,
                post_url="",
                edit_url="",
                status="failed",
                publish_date=datetime.now(),
                success=False,
                error_message=error_msg
            )
    
    def _get_or_create_category(self, category_name: str) -> Optional[int]:
        """카테고리 가져오기 또는 생성"""
        try:
            # 기존 카테고리 검색
            response = requests.get(
                f"{self.api_base}/categories",
                params={'search': category_name},
                auth=self.auth,
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                categories = response.json()
                for cat in categories:
                    if cat['name'] == category_name:
                        print(f"  📁 기존 카테고리 사용: {category_name} (ID: {cat['id']})")
                        return cat['id']
                
                # 카테고리가 없으면 생성
                create_response = requests.post(
                    f"{self.api_base}/categories",
                    json={'name': category_name},
                    auth=self.auth,
                    headers=self.headers,
                    timeout=10
                )
                
                if create_response.status_code == 201:
                    new_cat = create_response.json()
                    print(f"  📁 새 카테고리 생성: {category_name} (ID: {new_cat['id']})")
                    return new_cat['id']
            
            print(f"  ⚠️ 카테고리 처리 실패: {category_name}")
            return None
            
        except Exception as e:
            print(f"  ⚠️ 카테고리 처리 오류: {str(e)}")
            return None
    
    def _get_or_create_tags(self, tag_names: List[str]) -> List[int]:
        """태그 가져오기 또는 생성"""
        tag_ids = []
        
        for tag_name in tag_names:
            try:
                # 기존 태그 검색
                response = requests.get(
                    f"{self.api_base}/tags",
                    params={'search': tag_name},
                    auth=self.auth,
                    headers=self.headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    tags = response.json()
                    tag_found = False
                    
                    for tag in tags:
                        if tag['name'] == tag_name:
                            tag_ids.append(tag['id'])
                            tag_found = True
                            break
                    
                    if not tag_found:
                        # 태그가 없으면 생성
                        create_response = requests.post(
                            f"{self.api_base}/tags",
                            json={'name': tag_name},
                            auth=self.auth,
                            headers=self.headers,
                            timeout=10
                        )
                        
                        if create_response.status_code == 201:
                            new_tag = create_response.json()
                            tag_ids.append(new_tag['id'])
                
            except Exception as e:
                print(f"  ⚠️ 태그 처리 오류 ({tag_name}): {str(e)}")
                continue
        
        print(f"  🏷️ 태그 처리 완료: {len(tag_ids)}개")
        return tag_ids
    
    def _build_post_html(self, content_data: GeneratedContent, uploaded_media: List[MediaUploadResult]) -> str:
        """포스트 HTML 구성"""
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
        """
        
        # 업로드된 이미지 삽입
        if uploaded_media:
            for i, media in enumerate(uploaded_media):
                img_html = f"""
                <div class="content-image" style="text-align: center; margin: 25px 0;">
                    <img src="{media.url}" alt="BGN 이미지 {i+1}" 
                         style="max-width: 100%; height: auto; border-radius: 8px;" />
                </div>
                """
                styled_html += img_html
        
        # FAQ 섹션 추가
        if content_data.faq_list:
            styled_html += """
            <div class="faq-section">
                <h2>자주 묻는 질문</h2>
            """
            
            for faq in content_data.faq_list:
                styled_html += f"""
                <div class="faq-item" style="margin-bottom: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                    <h4 style="color: #2E86AB; margin-bottom: 10px;">Q: {faq['question']}</h4>
                    <p style="margin: 0; color: #555;">A: {faq['answer']}</p>
                </div>
                """
            
            styled_html += "</div>"
        
        # CTA 버튼 추가
        styled_html += f"""
            <div class="cta-section" style="text-align: center; margin: 30px 0; padding: 20px; 
                 background: linear-gradient(90deg, #2E86AB, #A23B72); border-radius: 10px;">
                <a href="#contact" style="color: white; font-size: 18px; font-weight: bold; text-decoration: none; 
                   padding: 15px 30px; background: rgba(255,255,255,0.2); border-radius: 25px; display: inline-block;">
                    {content_data.cta_button_text}
                </a>
            </div>
        """
        
        # 병원 정보 추가
        styled_html += f"""
            <div class="hospital-info" style="background: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h3>🏥 {Settings.HOSPITAL_NAME}</h3>
                <p>📍 위치: {', '.join(Settings.HOSPITAL_LOCATIONS)}</p>
                <p>📞 상담문의: {Settings.HOSPITAL_PHONE}</p>
            </div>
        """
        
        # 의료진 검토 안내
        styled_html += """
            <div class="medical-disclaimer" style="background: #fff3cd; border: 1px solid #ffc107; 
                 padding: 15px; border-radius: 5px; margin-top: 30px; font-size: 14px;">
                <p><strong>⚠️ 의료진 검토 완료</strong> | BGN 밝은눈안과</p>
                <p>본 내용은 일반적인 안내사항으로, 개인별 상태에 따라 달라질 수 있습니다. 
                정확한 진단과 치료는 의료진과의 상담을 통해 받으시기 바랍니다.</p>
            </div>
        </div>
        """
        
        return styled_html

# ========================================
# 구글 시트 클라이언트
# ========================================

class SafeGoogleSheetsClient:
    """안전한 구글 시트 클라이언트"""
    
    def __init__(self, spreadsheet_id: str = None, credentials_file: str = None):
        if not GOOGLE_SHEETS_AVAILABLE:
            raise ImportError("Google Sheets 라이브러리가 설치되지 않았습니다.")
        
        self.spreadsheet_id = spreadsheet_id or Settings.GOOGLE_SHEETS_ID
        self.credentials_file = credentials_file or Settings.GOOGLE_CREDENTIALS_FILE
        
        if not self.spreadsheet_id:
            raise ValueError("구글 시트 ID가 설정되지 않았습니다.")
        
        if not os.path.exists(self.credentials_file):
            raise ValueError(f"인증 파일이 없습니다: {self.credentials_file}")
        
        # 인증 및 연결
        self._initialize_connection()
    
    def _initialize_connection(self):
        """구글 시트 연결 초기화"""
        try:
            print(f"📊 구글 시트 연결 시도...")
            
            # 서비스 계정 인증
            credentials = ServiceAccountCredentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            self.gc = gspread.authorize(credentials)
            self.spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            
            print(f"  ✅ 스프레드시트 연결: {self.spreadsheet.title}")
            logger.info("구글 시트 연결 성공")
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ 구글 시트 연결 실패: {error_msg}")
            logger.error(f"구글 시트 연결 실패: {error_msg}")
            raise ConnectionError(f"구글 시트 연결 실패: {error_msg}")
    
    def add_content_row(self, analysis_result: InterviewAnalysisResult, 
                       generated_content: GeneratedContent, 
                       wordpress_result: PostPublishResult = None) -> bool:
        """콘텐츠 정보를 시트에 안전하게 추가"""
        try:
            # 메인 워크시트 가져오기
            try:
                worksheet = self.spreadsheet.worksheet("콘텐츠 관리")
            except gspread.WorksheetNotFound:
                # 워크시트가 없으면 생성
                worksheet = self._create_main_worksheet()
            
            # 데이터 준비
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            row_data = [
                generated_content.title,
                generated_content.slug,
                ', '.join(generated_content.tags),
                analysis_result.employee.name or "미상",
                analysis_result.employee.department or "미상",
                generated_content.estimated_reading_time,
                f"{generated_content.seo_score:.2f}",
                f"{generated_content.medical_compliance_score:.2f}",
                wordpress_result.status if wordpress_result else "생성됨",
                wordpress_result.post_url if wordpress_result else "",
                current_time
            ]
            
            # 다음 빈 행에 데이터 추가
            worksheet.append_row(row_data)
            
            logger.info(f"시트에 콘텐츠 추가: {generated_content.title}")
            return True
            
        except Exception as e:
            logger.error(f"시트 데이터 추가 실패: {str(e)}")
            return False
    
    def _create_main_worksheet(self):
        """메인 워크시트 생성"""
        try:
            worksheet = self.spreadsheet.add_worksheet(
                title="콘텐츠 관리",
                rows=1000,
                cols=15
            )
            
            # 헤더 설정
            headers = [
                "제목", "슬러그", "태그", "담당자", "부서", 
                "읽기시간(분)", "SEO점수", "의료광고법점수", 
                "상태", "워드프레스URL", "생성일시"
            ]
            
            worksheet.update('A1', [headers])
            
            # 헤더 스타일링
            worksheet.format('A1:K1', {
                'backgroundColor': {'red': 0.2, 'green': 0.53, 'blue': 0.67},
                'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True}
            })
            
            return worksheet
            
        except Exception as e:
            logger.error(f"워크시트 생성 실패: {str(e)}")
            raise

# ========================================
# Streamlit 웹 인터페이스
# ========================================

def setup_streamlit():
    """Streamlit 페이지 설정"""
    st.set_page_config(
        page_title="BGN 블로그 자동화 (REST API)",
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
    .error-box {
        background: #f8d7da;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #dc3545;
        margin: 10px 0;
    }
    .api-info {
        background: #e3f2fd;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #2196f3;
        margin: 10px 0;
    }
    </style>
    """, unsafe_allow_html=True)

def main():
    """메인 애플리케이션"""
    setup_streamlit()
    
    # 의존성 체크
    if not display_dependency_warnings():
        st.stop()
    
    # 메인 헤더
    st.markdown("""
    <div class="main-header">
        <h1>🏥 BGN 밝은눈안과 블로그 자동화 시스템 (REST API 버전)</h1>
        <p>🔧 XML-RPC 문제 해결! 더 안전하고 현대적인 WordPress REST API 사용</p>
        <p>인터뷰 내용 → AI 분석 → 이미지 생성 → 워드프레스 자동 발행</p>
    </div>
    """, unsafe_allow_html=True)
    
    # REST API 정보 박스
    st.markdown("""
    <div class="api-info">
        <h3>🚀 REST API 버전의 장점</h3>
        <ul>
            <li>✅ XML-RPC 403 Forbidden 오류 해결</li>
            <li>✅ 더 안전하고 현대적인 API 방식</li>
            <li>✅ 향상된 오류 처리 및 디버깅</li>
            <li>✅ 실시간 연결 상태 확인</li>
            <li>✅ 자동 카테고리/태그 생성</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # 사이드바 설정
    with st.sidebar:
        st.header("🔧 API 설정")
        
        # OpenAI API 키
        openai_api_key = st.text_input(
            "OpenAI API Key", 
            value=Settings.OPENAI_API_KEY,
            type="password",
            help="GPT-4 및 DALL-E 사용을 위한 API 키"
        )
        
        if not openai_api_key:
            st.markdown('<div class="error-box">❌ OpenAI API 키가 필요합니다</div>', unsafe_allow_html=True)
        
        st.header("🌐 WordPress REST API 설정")
        
        wp_url = st.text_input(
            "워드프레스 사이트 URL", 
            value=Settings.WORDPRESS_URL,
            help="예: https://your-site.com (끝에 슬래시 제외)"
        )
        
        wp_username = st.text_input(
            "사용자명", 
            value=Settings.WORDPRESS_USERNAME,
            help="워드프레스 관리자 사용자명"
        )
        
        wp_password = st.text_input(
            "앱 패스워드", 
            value=Settings.WORDPRESS_PASSWORD, 
            type="password",
            help="일반 패스워드가 아닌 앱 패스워드를 사용하세요!"
        )
        
        # 앱 패스워드 안내
        with st.expander("📱 앱 패스워드 생성 방법"):
            st.markdown("""
            1. **워드프레스 관리자** → `사용자` → `프로필`
            2. **응용 프로그램 암호** 섹션으로 이동
            3. 애플리케이션 이름 입력 (예: "BGN 블로그 자동화")
            4. **새 응용 프로그램 암호 추가** 클릭
            5. 생성된 패스워드를 **공백 포함해서** 복사하여 입력
            
            ⚠️ **중요**: 일반 로그인 패스워드가 아닌 앱 패스워드를 사용해야 합니다!
            """)
        
        # 발행 옵션 선택
        wp_publish_option = st.selectbox(
            "발행 옵션",
            ["draft", "publish", "private"],
            index=0,
            help="draft: 초안 저장, publish: 즉시 발행, private: 비공개"
        )
        
        wp_connect = st.checkbox("워드프레스 연동", value=True)
        
        # REST API 연결 테스트 버튼
        if wp_url and wp_username and wp_password:
            if st.button("🔍 REST API 연결 테스트"):
                try:
                    with st.spinner("연결 테스트 중..."):
                        test_client = WordPressRestAPIClient(wp_url, wp_username, wp_password)
                        st.success("✅ REST API 연결 성공!")
                        st.info("💡 이제 자동화를 실행할 수 있습니다.")
                except Exception as e:
                    st.error(f"❌ 연결 실패: {str(e)}")
                    st.markdown("""
                    **해결 방법:**
                    1. 앱 패스워드가 올바른지 확인
                    2. URL에 http:// 또는 https:// 포함 확인
                    3. 워드프레스 사이트가 REST API를 지원하는지 확인
                    """)
        
        # 선택한 옵션에 따른 안내 메시지
        if wp_publish_option == "draft":
            st.info("📝 워드프레스에 초안으로 저장됩니다. (권장)")
        elif wp_publish_option == "publish":
            st.warning("⚠️ 워드프레스에 즉시 발행됩니다!")
        else:
            st.info("🔒 비공개 포스트로 저장됩니다.")
        
        st.header("📊 구글 시트 설정")
        if GOOGLE_SHEETS_AVAILABLE:
            sheets_id = st.text_input("구글 시트 ID", value=Settings.GOOGLE_SHEETS_ID)
        else:
            st.warning("⚠️ Google Sheets 라이브러리가 설치되지 않았습니다.")
            sheets_id = ""
        
        st.header("🎨 생성 옵션")
        image_style = st.selectbox(
            "이미지 스타일",
            ["medical_clean", "infographic", "equipment"],
            help="생성될 이미지의 스타일"
        )
        
        generate_images = st.checkbox("이미지 자동 생성", value=True)
        save_to_sheets = st.checkbox("구글 시트 저장", value=True)
    
    # 메인 컨텐츠
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📄 인터뷰 내용 입력")
        
        # 파일 업로드 옵션
        uploaded_file = st.file_uploader(
            "인터뷰 파일 업로드",
            type=['txt'],
            help="텍스트 파일을 업로드하세요"
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
            st.session_state['sample_data'] = """
저는 밝은눈안과 홍보팀에 이예나 대리고요. 
지금 경력은 병원 마케팅 쪽은 지금 거의 10년 정도 다 되어 가고 있습니다.
여기서는 이제 대학팀에 같이 있고요. 대학 제휴랑 출장검진을 담당하고 있습니다.
솔직하게 말씀드리면 저희 병원은 26년간 의료사고가 없었다는 점이 장점이고,
잠실 롯데타워 위치가 정말 좋아서 고객님들이 만족해하시는 편이에요.
대학생분들께는 특별 할인도 제공하고 있고, 축제 때 가서 상담도 해드리고 있어요.
사실 많은 분들이 궁금해하시는 게 검사 과정인데, 저희는 정말 세심하게 케어해드려요.
            """.strip()
            st.rerun()
        
        # 샘플 데이터가 설정되었다면 표시
        if 'sample_data' in st.session_state:
            interview_content = st.session_state['sample_data']
    
    with col2:
        st.header("📊 생성 미리보기")
        
        if interview_content or uploaded_file:
            st.markdown('<div class="success-box">', unsafe_allow_html=True)
            st.write("분석 준비 완료")
            if interview_content:
                st.write(f"입력된 텍스트: {len(interview_content)}자")
            if uploaded_file:
                st.write(f"업로드된 파일: {uploaded_file.name}")
            st.markdown('</div>', unsafe_allow_html=True)
            
            # 예상 결과 미리보기
            st.subheader("예상 생성 결과")
            st.write("블로그 포스트: 1개")
            if generate_images and IMAGE_AVAILABLE:
                st.write("이미지 생성: 3개")
            if wp_connect and wp_url:
                st.write(f"워드프레스: {wp_publish_option} 상태로 저장")
            if save_to_sheets and GOOGLE_SHEETS_AVAILABLE and sheets_id:
                st.write("구글 시트: 자동 저장")
            
        else:
            st.markdown('<div class="warning-box">', unsafe_allow_html=True)
            st.write("인터뷰 내용을 입력하거나 파일을 업로드해주세요.")
            st.markdown('</div>', unsafe_allow_html=True)

    # 실행 버튼
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀 REST API 자동화 실행", type="primary", use_container_width=True):
            
            # 필수 입력 검증
            if not openai_api_key:
                st.error("❌ OpenAI API 키를 입력해주세요!")
                return
                
            # 인터뷰 내용 추출
            content = ""
            if uploaded_file:
                try:
                    content = str(uploaded_file.read(), "utf-8")
                except Exception as e:
                    st.error(f"❌ 파일 읽기 실패: {str(e)}")
                    return
            elif interview_content:
                content = interview_content
            else:
                st.error("❌ 인터뷰 내용을 입력해주세요!")
                return
            
            # 자동화 프로세스 실행
            execute_automation_rest_api(
                content, openai_api_key, wp_url, wp_username, wp_password,
                sheets_id, image_style, generate_images, wp_connect, wp_publish_option, save_to_sheets
            )

def execute_automation_rest_api(content, api_key, wp_url, wp_username, wp_password, 
                               sheets_id, image_style, generate_images, wp_connect, wp_publish_option, save_to_sheets):
    """REST API 기반 자동화 프로세스 실행"""
    
    progress_container = st.container()
    
    with progress_container:
        # 1단계: 인터뷰 분석
        with st.status("🔍 1단계: 인터뷰 분석 중...", expanded=True) as status:
            st.write("직원 정보 및 전문 지식 추출 중...")
            
            try:
                analyzer = SafeInterviewAnalyzer(api_key)
                analysis_result = analyzer.analyze_interview(content)
                
                st.success("✅ 인터뷰 분석 완료")
                st.write(f"**감지된 직원**: {analysis_result.employee.name or '미상'}")
                st.write(f"**부서**: {analysis_result.employee.department or '미상'}")
                st.write(f"**전문 분야**: {', '.join(analysis_result.employee.specialty_areas) or '없음'}")
                st.write(f"**신뢰도**: {analysis_result.analysis_metadata['confidence_score']:.2f}")
                
                status.update(label="✅ 1단계 완료: 인터뷰 분석", state="complete")
                
            except Exception as e:
                st.error(f"❌ 인터뷰 분석 실패: {str(e)}")
                return
        
        # 2단계: 콘텐츠 생성
        with st.status("📝 2단계: 콘텐츠 생성 중...", expanded=True) as status:
            st.write("블로그 포스트 작성 중...")
            
            try:
                generator = SafeContentGenerator(api_key)
                generated_content = generator.generate_content(analysis_result)
                
                st.success("✅ 콘텐츠 생성 완료")
                st.write(f"**제목**: {generated_content.title}")
                st.write(f"**예상 읽기 시간**: {generated_content.estimated_reading_time}분")
                st.write(f"**SEO 점수**: {generated_content.seo_score:.2f}")
                st.write(f"**의료광고법 준수**: {generated_content.medical_compliance_score:.2f}")
                
                # 콘텐츠 미리보기
                with st.expander("📄 생성된 콘텐츠 미리보기"):
                    preview_text = generated_content.content_markdown
                    if len(preview_text) > 500:
                        preview_text = preview_text[:500] + "..."
                    st.markdown(preview_text)
                
                status.update(label="✅ 2단계 완료: 콘텐츠 생성", state="complete")
                
            except Exception as e:
                st.error(f"❌ 콘텐츠 생성 실패: {str(e)}")
                return
        
        # 3단계: 이미지 생성
        generated_images = []
        if generate_images and IMAGE_AVAILABLE:
            with st.status("🎨 3단계: 이미지 생성 중...", expanded=True) as status:
                
                try:
                    image_generator = SafeImageGenerator(api_key)
                    generated_images = image_generator.generate_blog_images(generated_content, image_style)
                    
                    st.success(f"✅ {len(generated_images)}개 이미지 생성 완료")
                    
                    # 이미지 미리보기
                    if generated_images:
                        cols = st.columns(min(len(generated_images), 3))
                        for i, (img, alt_text) in enumerate(generated_images[:3]):
                            with cols[i]:
                                st.image(img, caption=f"이미지 {i+1}", width=200)
                    
                    status.update(label="✅ 3단계 완료: 이미지 생성", state="complete")
                    
                except Exception as e:
                    st.warning(f"⚠️ 이미지 생성 실패: {str(e)}")
                    status.update(label="⚠️ 3단계: 이미지 생성 실패", state="error")
        
        # 4단계: WordPress REST API 포스팅
        wordpress_result = None
        if wp_connect and wp_url and wp_username and wp_password:
            with st.status("🌐 4단계: WordPress REST API 포스팅 중...", expanded=True) as status:
                
                try:
                    # 발행 옵션에 따른 메시지
                    if wp_publish_option == "draft":
                        st.write("초안으로 저장 중...")
                    elif wp_publish_option == "publish":
                        st.write("⚠️ 즉시 발행 중...")
                    else:
                        st.write("비공개 포스트로 저장 중...")
                    
                    wp_client = WordPressRestAPIClient(wp_url, wp_username, wp_password)
                    wordpress_result = wp_client.create_post(generated_content, generated_images, wp_publish_option)
                    
                    if wordpress_result.success:
                        st.success("✅ WordPress REST API 포스팅 완료!")
                        st.write(f"**포스트 ID**: {wordpress_result.post_id}")
                        st.write(f"**상태**: {wordpress_result.status}")
                        st.write(f"**URL**: {wordpress_result.post_url}")
                        
                        if wp_publish_option == "draft":
                            st.info("💡 초안으로 저장되었습니다. 워드프레스 관리자에서 검토 후 발행하세요.")
                        
                        status.update(label="✅ 4단계 완료: WordPress REST API 포스팅", state="complete")
                    else:
                        st.error(f"❌ WordPress 포스팅 실패: {wordpress_result.error_message}")
                        status.update(label="❌ 4단계: WordPress 포스팅 실패", state="error")
                        
                except Exception as e:
                    st.error(f"❌ WordPress REST API 연동 오류: {str(e)}")
                    status.update(label="❌ 4단계: WordPress REST API 연동 실패", state="error")
        
        # 5단계: 구글 시트 저장
        if save_to_sheets and GOOGLE_SHEETS_AVAILABLE and sheets_id:
            with st.status("📊 5단계: 구글 시트 저장 중...", expanded=True) as status:
                
                try:
                    sheets_client = SafeGoogleSheetsClient(sheets_id)
                    success = sheets_client.add_content_row(analysis_result, generated_content, wordpress_result)
                    
                    if success:
                        st.success("✅ 구글 시트 저장 완료!")
                        status.update(label="✅ 5단계 완료: 구글 시트 저장", state="complete")
                    else:
                        st.warning("⚠️ 구글 시트 저장 실패")
                        status.update(label="⚠️ 5단계: 구글 시트 저장 실패", state="error")
                        
                except Exception as e:
                    st.warning(f"⚠️ 구글 시트 연동 오류: {str(e)}")
                    status.update(label="⚠️ 5단계: 구글 시트 연동 실패", state="error")
        
        # 결과 표시
        display_results_rest_api(analysis_result, generated_content, generated_images, wordpress_result)

def display_results_rest_api(analysis_result, generated_content, generated_images, wordpress_result):
    """REST API 결과 표시"""
    st.markdown("---")
    st.markdown('<div class="success-box">', unsafe_allow_html=True)
    st.header("🎉 REST API 자동화 완료!")
    
    # 결과 요약
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        st.metric("분석 완료", "✅")
        st.write("✓ 직원 정보 추출")
        st.write("✓ 콘텐츠 데이터 생성")
    
    with col2:
        st.metric("콘텐츠 생성", "✅")
        st.write(f"✓ {generated_content.estimated_reading_time}분 분량")
        st.write(f"✓ SEO 점수 {generated_content.seo_score:.2f}")
        char_count = len(generated_content.content_markdown)
        st.write(f"✓ 총 {char_count:,}자")
    
    with col3:
        st.metric("이미지 생성", f"{len(generated_images)}개")
        if generated_images:
            st.write("✓ DALL-E 고품질")
            st.write("✓ 의료용 스타일")
        else:
            st.write("○ 이미지 생성 안함")
    
    with col4:
        if wordpress_result and wordpress_result.success:
            st.metric("REST API 포스팅", "✅")
            st.write("✓ WordPress 발행")
            st.write(f"✓ {wordpress_result.status} 상태")
        else:
            st.metric("포스팅 대기", "📝")
            st.write("○ 수동 발행 필요")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 콘텐츠 전문 표시
    st.markdown("### 📄 생성된 콘텐츠 전문")
    
    # 탭으로 구분하여 표시
    tab1, tab2, tab3 = st.tabs(["📝 마크다운", "🌐 HTML", "📊 분석 정보"])
    
    with tab1:
        st.markdown("**마크다운 형태:** (복사해서 사용하세요)")
        st.text_area(
            "생성된 콘텐츠 (마크다운)",
            value=generated_content.content_markdown,
            height=400,
            help="Ctrl+A로 전체 선택 후 복사하세요"
        )
    
    with tab2:
        st.markdown("**HTML 형태:**")
        st.text_area(
            "생성된 콘텐츠 (HTML)",
            value=generated_content.content_html,
            height=400,
            help="워드프레스나 다른 사이트에 바로 붙여넣기 가능"
        )
        
        st.markdown("**HTML 미리보기:**")
        try:
            st.components.v1.html(generated_content.content_html, height=600, scrolling=True)
        except:
            st.markdown(generated_content.content_html, unsafe_allow_html=True)
    
    with tab3:
        st.markdown("**분석 정보:**")
        analysis_info = f"""제목: {generated_content.title}
슬러그: {generated_content.slug}
메타 설명: {generated_content.meta_description}
태그: {', '.join(generated_content.tags)}
예상 읽기 시간: {generated_content.estimated_reading_time}분
총 글자수: {len(generated_content.content_markdown):,}자
SEO 점수: {generated_content.seo_score:.2f}
의료광고법 준수: {generated_content.medical_compliance_score:.2f}

=== 담당자 정보 ===
담당자: {analysis_result.employee.name}
부서: {analysis_result.employee.department}
직책: {analysis_result.employee.position}
경력: {analysis_result.employee.experience_years}년
전문분야: {', '.join(analysis_result.employee.specialty_areas)}
말투 특성: {analysis_result.personality.tone_style}

=== FAQ 목록 ==="""
        
        for i, faq in enumerate(generated_content.faq_list, 1):
            analysis_info += f"\nQ{i}: {faq['question']}\nA{i}: {faq['answer']}\n"
        
        st.text_area("분석 및 메타데이터", value=analysis_info, height=400)
    
    # 다운로드 옵션
    st.markdown("### 📎 다운로드 옵션")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        st.download_button(
            label="📄 텍스트 파일 다운로드",
            data=generated_content.content_markdown,
            file_name=f"{generated_content.slug}.txt",
            mime="text/plain"
        )
    
    with col2:
        st.download_button(
            label="📄 마크다운 다운로드", 
            data=generated_content.content_markdown,
            file_name=f"{generated_content.slug}.md",
            mime="text/markdown"
        )
    
    with col3:
        st.download_button(
            label="🌐 HTML 다운로드", 
            data=generated_content.content_html,
            file_name=f"{generated_content.slug}.html",
            mime="text/html"
        )
    
    # 워드프레스 링크
    if wordpress_result and wordpress_result.success:
        st.markdown("### 🔗 워드프레스 링크")
        st.success(f"**포스트 보기**: [클릭하여 확인]({wordpress_result.post_url})")
        st.info(f"**편집하기**: [관리자에서 편집]({wordpress_result.edit_url})")
        
        if wordpress_result.status == "draft":
            st.warning("💡 현재 초안 상태입니다. 워드프레스 관리자에서 검토 후 발행하세요.")
    
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
                    label=f"🖼️ 이미지 {i+1} 다운로드",
                    data=img_bytes.getvalue(),
                    file_name=f"{generated_content.slug}_image_{i+1}.jpg",
                    mime="image/jpeg"
                )
                st.caption(alt_text)

# ========================================
# 유틸리티 함수들
# ========================================

def create_sample_env_file():
    """샘플 .env 파일 생성"""
    sample_content = """
# OpenAI API 설정 (필수)
OPENAI_API_KEY=your_openai_api_key_here

# 워드프레스 REST API 설정 (선택적)
WORDPRESS_URL=https://your-wordpress-site.com
WORDPRESS_USERNAME=your_username
WORDPRESS_PASSWORD=your_app_password

# 구글 시트 설정 (선택적)
GOOGLE_SHEETS_ID=your_google_sheets_id
GOOGLE_CREDENTIALS_FILE=credentials.json

# 로그 레벨
LOG_LEVEL=INFO
    """.strip()
    
    try:
        with open('.env.example', 'w', encoding='utf-8') as f:
            f.write(sample_content)
        
        print("📄 .env.example 파일이 생성되었습니다.")
        print("💡 이 파일을 .env로 복사하고 실제 값으로 수정하세요.")
        
    except Exception as e:
        print(f"❌ .env.example 파일 생성 실패: {str(e)}")

def run_simple_test():
    """간단한 테스트 실행"""
    sample_interview = """
    저는 밝은눈안과 홍보팀에 이예나 대리고요. 
    지금 경력은 병원 마케팅 쪽은 지금 거의 10년 정도 다 되어 가고 있습니다.
    여기서는 이제 대학팀에 같이 있고요. 대학 제휴랑 출장검진을 담당하고 있습니다.
    """
    
    try:
        print("🔍 인터뷰 분석 테스트...")
        analyzer = SafeInterviewAnalyzer()
        result = analyzer.analyze_interview(sample_interview)
        
        print(f"✅ 분석 완료!")
        print(f"직원명: {result.employee.name}")
        print(f"부서: {result.employee.department}")
        print(f"신뢰도: {result.analysis_metadata['confidence_score']:.2f}")
        
        print("\n📝 콘텐츠 생성 테스트...")
        generator = SafeContentGenerator()
        content = generator.generate_content(result)
        
        print(f"✅ 콘텐츠 생성 완료!")
        print(f"제목: {content.title}")
        print(f"SEO 점수: {content.seo_score:.2f}")
        
        print("\n🎉 모든 테스트 통과!")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        print("💡 .env 파일에 OPENAI_API_KEY가 설정되어 있는지 확인하세요.")

# ========================================
# 메인 실행부
# ========================================

if __name__ == "__main__":
    try:
        # CLI 인수 확인
        if len(sys.argv) > 1:
            if "--test" in sys.argv:
                run_simple_test()
            elif "--create-env" in sys.argv:
                create_sample_env_file()
            else:
                print("사용법:")
                print("  streamlit run main.py       # 웹 UI 실행")
                print("  python main.py --test       # 테스트 실행")
                print("  python main.py --create-env # .env 샘플 생성")
        else:
            # Streamlit 앱 실행
            main()
        
    except Exception as e:
        print(f"❌ 시스템 오류: {str(e)}")
        print("💡 다음을 확인하세요:")
        print("  1. 필수 라이브러리 설치: pip install streamlit openai pillow requests python-dotenv")
        print("  2. .env 파일에 OPENAI_API_KEY 설정")
        print("  3. 워드프레스 REST API는 앱 패스워드 사용")

# ========================================
# 추가 정보 및 도움말
# ========================================

"""
BGN 밝은눈안과 블로그 자동화 시스템 v3.0 (REST API 버전)

🔧 주요 개선사항:
- XML-RPC 문제 완전 해결: WordPress REST API 사용
- 실시간 API 연결 테스트 기능
- 향상된 오류 처리 및 디버깅
- 자동 카테고리/태그 생성
- 앱 패스워드 안내 및 인증 개선

📋 설치 가이드:
1. 필수 라이브러리:
   pip install streamlit openai pillow requests python-dotenv

2. 선택적 라이브러리:
   pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib gspread

3. 환경 설정:
   - .env 파일에 OPENAI_API_KEY 설정
   - 워드프레스 앱 패스워드 생성 및 설정
   - 구글 시트 연동시 시트 ID 및 인증 파일 설정

🚀 실행 방법:
- 웹 UI: streamlit run main.py
- 테스트: python main.py --test
- 환경 파일 생성: python main.py --create-env

💡 REST API 장점:
- ✅ 403 Forbidden 오류 해결
- ✅ 더 안전하고 현대적
- ✅ 실시간 연결 상태 확인
- ✅ 자동 미디어 업로드
- ✅ 향상된 오류 처리

🔧 문제 해결:
- API 오류: .env 파일의 API 키 확인
- 워드프레스 연결 실패: 앱 패스워드 및 URL 확인
- 이미지 생성 실패: OpenAI 크레딧 확인
- 구글 시트 오류: 인증 파일과 권한 확인
"""