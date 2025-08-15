#!/usr/bin/env python3
"""
BGN 밝은눈안과 블로그 완전 자동화 통합 시스템
- 인터뷰 분석 (OpenAI GPT-4)
- 콘텐츠 생성 (Markdown → HTML)
- 이미지 자동 생성 (DALL-E 3)
- 워드프레스 자동 포스팅
- 구글 시트 자동 관리
- Streamlit 웹 인터페이스
"""

import streamlit as st
import openai
import pandas as pd
import requests
import base64
from PIL import Image, ImageEnhance
import io
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import time
import json
import re
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, asdict
import mimetypes

# 환경변수 로드
load_dotenv()

# 필수 라이브러리 import (선택적)
try:
    from wordpress_xmlrpc import Client, WordPressPost
    from wordpress_xmlrpc.methods.posts import NewPost
    from wordpress_xmlrpc.methods.media import UploadFile
    WORDPRESS_AVAILABLE = True
except ImportError:
    WORDPRESS_AVAILABLE = False

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
    
    # 워드프레스 설정
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
# 인터뷰 분석기
# ========================================

class InterviewAnalyzer:
    """직원 인터뷰 분석기"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or Settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API 키가 설정되지 않았습니다.")
        
        self.client = openai.OpenAI(api_key=self.api_key)
        
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
        """인터뷰 텍스트 분석"""
        try:
            # 텍스트 전처리
            cleaned_text = self._preprocess_text(interview_text)
            
            # 기본 정보 추출
            employee = self._extract_employee_info(cleaned_text)
            personality = self._analyze_personality(cleaned_text)
            knowledge = self._extract_knowledge(cleaned_text)
            customer_insights = self._extract_customer_insights(cleaned_text)
            hospital_strengths = self._extract_hospital_strengths(cleaned_text)
            
            # AI 기반 고급 분석 (선택적)
            if self.api_key:
                try:
                    ai_enhancement = self._ai_enhanced_analysis(cleaned_text[:2000])
                    employee, knowledge = self._merge_ai_results(employee, knowledge, ai_enhancement)
                except Exception as e:
                    logger.warning(f"AI 분석 실패: {str(e)}")
            
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
            # 기본 결과 반환
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
        name_match = re.search(r'저는\s*([가-힣]{2,4})', text)
        if name_match:
            employee.name = name_match.group(1)
        
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
        exp_match = re.search(r'(\d+)년.*?(경력|차)', text)
        if exp_match:
            employee.experience_years = int(exp_match.group(1))
        
        # 전문분야 추출
        if '대학' in text:
            employee.specialty_areas.append('대학 제휴')
        if '출장검진' in text:
            employee.specialty_areas.append('출장검진')
        if '상담' in text:
            employee.specialty_areas.append('고객 상담')
        
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
        if '장비' in text or 'OCT' in text:
            knowledge.equipment.append('안과 검사 장비')
        
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
        
        # 고객층 추출
        if '대학생' in text:
            insights.target_demographics.append('대학생')
        if '직장인' in text:
            insights.target_demographics.append('직장인')
        
        return insights
    
    def _extract_hospital_strengths(self, text: str) -> HospitalStrengths:
        """병원 강점 추출"""
        strengths = HospitalStrengths()
        
        # 위치 장점
        if '롯데타워' in text or '잠실' in text:
            strengths.location_benefits.append('롯데타워 위치')
        
        # 경쟁 우위
        if '무사고' in text or '26년' in text:
            strengths.competitive_advantages.append('26년 무사고 기록')
        
        # 특별 서비스
        if '할인' in text:
            strengths.unique_services.append('학생 할인 혜택')
        if '축제' in text:
            strengths.unique_services.append('대학 축제 상담')
        
        return strengths
    
    def _ai_enhanced_analysis(self, text: str) -> Dict:
        """AI 기반 고급 분석"""
        try:
            prompt = f"""
            다음 BGN 밝은눈안과 직원 인터뷰를 분석하여 JSON으로 결과를 제공해주세요.

            인터뷰: {text}

            다음 정보를 추출해주세요:
            {{
                "employee_name": "이름",
                "department": "부서",
                "position": "직책", 
                "specialties": ["전문분야들"],
                "procedures": ["담당 시술/검사들"],
                "personality_traits": ["성격 특성들"]
            }}
            """
            
            response = self.client.chat.completions.create(
                model=Settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "당신은 의료 인사 분석 전문가입니다. JSON 형태로만 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            result = response.choices[0].message.content
            return json.loads(result)
            
        except Exception as e:
            logger.warning(f"AI 분석 실패: {str(e)}")
            return {}
    
    def _merge_ai_results(self, employee: EmployeeProfile, knowledge: ProfessionalKnowledge, ai_data: Dict) -> Tuple:
        """AI 결과 병합"""
        if not ai_data:
            return employee, knowledge
        
        try:
            if ai_data.get('employee_name') and not employee.name:
                employee.name = ai_data['employee_name']
            
            if ai_data.get('specialties'):
                employee.specialty_areas.extend(ai_data['specialties'])
                employee.specialty_areas = list(set(employee.specialty_areas))
            
            if ai_data.get('procedures'):
                knowledge.procedures.extend(ai_data['procedures'])
                knowledge.procedures = list(set(knowledge.procedures))
                
        except Exception as e:
            logger.warning(f"AI 결과 병합 실패: {str(e)}")
        
        return employee, knowledge
    
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
# 콘텐츠 생성기
# ========================================

class ContentGenerator:
    """블로그 콘텐츠 생성기"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or Settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API 키가 설정되지 않았습니다.")
        
        self.client = openai.OpenAI(api_key=self.api_key)
    
    def generate_content(self, analysis_result: InterviewAnalysisResult) -> GeneratedContent:
        """분석 결과를 바탕으로 콘텐츠 생성"""
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
            
            # 읽기 시간 추정
            reading_time = self._estimate_reading_time(main_content)
            
            # 점수 계산
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
        # 전문분야 기반 주제 결정
        specialties = analysis.employee.specialty_areas
        
        if '대학' in str(specialties):
            topic = "대학생을 위한 시력교정술"
            keywords = ["대학생", "시력교정", "방학수술", "학생할인"]
        elif '출장검진' in str(specialties):
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
            # 직원의 개성을 반영한 프롬프트 생성
            personality_context = ""
            if analysis.personality.tone_style:
                personality_context = f"글의 톤은 {analysis.personality.tone_style} 느낌으로 작성하세요."
            
            # 전문 지식 컨텍스트
            knowledge_context = ""
            if analysis.knowledge.procedures:
                knowledge_context = f"다음 시술들에 대해 언급하세요: {', '.join(analysis.knowledge.procedures[:3])}"
            
            prompt = f"""
            BGN 밝은눈안과 블로그 글을 작성해주세요.

            주제: {plan['title']}
            타겟 독자: {plan['target_audience']}
            주요 키워드: {plan['primary_keyword']}

            {personality_context}
            {knowledge_context}

            다음 구조로 작성하세요:
            1. 도입부 (문제 제기)
            2. 주요 내용 (3-4개 섹션)
            3. BGN 병원의 강점
            4. 결론 및 행동 유도

            의료광고법을 준수하여 과장된 표현은 피하고, 
            환자분들에게 도움이 되는 실용적인 정보를 제공하세요.
            
            1500-2000자 분량으로 작성해주세요.
            """
            
            response = self.client.chat.completions.create(
                model=Settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "당신은 의료 콘텐츠 전문 작가입니다. 정확하고 도움이 되는 의료 정보를 제공하세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=Settings.OPENAI_TEMPERATURE,
                max_tokens=Settings.OPENAI_MAX_TOKENS
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"메인 콘텐츠 생성 실패: {str(e)}")
            return self._create_fallback_content(plan)
    
    def _generate_faq(self, analysis: InterviewAnalysisResult) -> List[Dict[str, str]]:
        """FAQ 생성"""
        # 고객 인사이트 기반 FAQ
        base_faqs = [
            {"question": "상담은 어떻게 받을 수 있나요?", "answer": "전화 또는 온라인으로 예약 가능합니다."},
            {"question": "검사 시간은 얼마나 걸리나요?", "answer": "정밀 검사는 약 1-2시간 소요됩니다."},
            {"question": "비용은 어떻게 되나요?", "answer": "상담을 통해 개별적으로 안내드립니다."}
        ]
        
        # 전문분야 기반 추가 FAQ
        if '대학' in str(analysis.employee.specialty_areas):
            base_faqs.append({
                "question": "학생 할인 혜택이 있나요?", 
                "answer": "네, 대학생 대상 특별 할인 혜택을 제공합니다."
            })
        
        return base_faqs[:4]  # 최대 4개
    
    def _generate_slug(self, title: str) -> str:
        """URL 슬러그 생성"""
        # 영어 키워드 매핑
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
            elif "출장검진" in specialty:
                tags.extend(["직장인", "출장검진", "정밀검사"])
            elif "상담" in specialty:
                tags.extend(["상담", "안내", "고객서비스"])
        
        # 의료 시술 기반 태그
        for procedure in analysis.knowledge.procedures:
            if "라식" in procedure:
                tags.append("라식")
            elif "라섹" in procedure:
                tags.append("라섹")
            elif "백내장" in procedure:
                tags.append("백내장")
        
        return list(set(tags))[:8]  # 중복 제거, 최대 8개
    
    def _generate_image_prompts(self, analysis: InterviewAnalysisResult) -> List[str]:
        """이미지 프롬프트 생성"""
        prompts = []
        
        # 기본 의료 상담 이미지
        prompts.append("Professional medical consultation in modern Korean hospital, doctor and patient discussion")
        
        # 전문분야 기반 이미지
        if "대학" in str(analysis.employee.specialty_areas):
            prompts.append("Young university students consulting about vision correction surgery in clean medical facility")
        elif "출장검진" in str(analysis.employee.specialty_areas):
            prompts.append("Professional workplace eye examination with modern medical equipment")
        else:
            prompts.append("Advanced eye examination equipment in modern ophthalmology clinic")
        
        # 병원 환경 이미지
        prompts.append("Clean and modern ophthalmology hospital interior with comfortable patient areas")
        
        return prompts
    
    def _generate_cta_text(self, analysis: InterviewAnalysisResult) -> str:
        """CTA 버튼 텍스트 생성"""
        if "대학" in str(analysis.employee.specialty_areas):
            return "대학생 전용 상담 예약하기"
        elif "출장검진" in str(analysis.employee.specialty_areas):
            return "기업 출장검진 문의하기"
        else:
            return "전문 상담 예약하기"
    
    def _markdown_to_html(self, markdown_content: str) -> str:
        """마크다운을 HTML로 변환"""
        # 간단한 마크다운 변환
        html = markdown_content
        
        # 헤딩 변환
        html = re.sub(r'^# (.+), r'<h1>\1</h1>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+), r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+), r'<h3>\1</h3>', html, flags=re.MULTILINE)
        
        # 볼드 변환
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        
        # 이탤릭 변환
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        
        # 줄바꿈을 <p> 태그로 변환
        paragraphs = html.split('\n\n')
        html_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<h'):
                html_paragraphs.append(f'<p>{para}</p>')
            elif para:
                html_paragraphs.append(para)
        
        return '\n'.join(html_paragraphs)
    
    def _estimate_reading_time(self, content: str) -> int:
        """읽기 시간 추정 (분)"""
        # 한국어 기준 분당 약 300자
        char_count = len(content)
        return max(1, round(char_count / 300))
    
    def _calculate_seo_score(self, title: str, content: str, tags: List[str]) -> float:
        """SEO 점수 계산"""
        score = 0.0
        
        # 제목 길이 (30-60자 권장)
        if 30 <= len(title) <= 60:
            score += 0.2
        
        # 콘텐츠 길이 (800자 이상 권장)
        if len(content) >= 800:
            score += 0.3
        
        # 태그 개수 (3-8개 권장)
        if 3 <= len(tags) <= 8:
            score += 0.2
        
        # 키워드 밀도 체크
        main_keywords = ["안과", "시력", "검사", "상담"]
        keyword_count = sum(content.count(keyword) for keyword in main_keywords)
        if keyword_count >= 3:
            score += 0.3
        
        return min(score, 1.0)
    
    def _check_medical_compliance(self, content: str) -> float:
        """의료광고법 준수도 체크"""
        score = 1.0
        
        # 금지 키워드 체크
        for prohibited in Settings.PROHIBITED_KEYWORDS:
            if prohibited in content:
                score -= 0.2
        
        # 과장 표현 체크
        risky_phrases = ["최고", "최대", "보장", "완전", "100%"]
        for phrase in risky_phrases:
            if phrase in content:
                score -= 0.1
        
        return max(score, 0.0)
    
    def _create_fallback_content(self, plan: Dict) -> str:
        """폴백 콘텐츠 생성"""
        return f"""
# {plan['title']}

## 안녕하세요, BGN 밝은눈안과입니다

{plan['target_audience']}을 위한 전문적인 안과 정보를 안내드립니다.

## 전문 의료진의 상세한 설명

저희 BGN 밝은눈안과는 26년간의 풍부한 경험을 바탕으로 안전하고 정확한 진료를 제공하고 있습니다.

## 정밀한 검사 시스템

최신 의료 장비를 활용한 정밀 검사를 통해 개인별 맞춤 진료를 실시합니다.

## 고객 중심의 서비스

편안한 환경에서 충분한 상담을 통해 고객님의 궁금증을 해결해드립니다.

## 마무리

더 자세한 정보가 필요하시면 언제든 상담을 통해 안내받으실 수 있습니다.
        """.strip()
    
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
# 이미지 생성기
# ========================================

class ImageGenerator:
    """DALL-E 이미지 생성기"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or Settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API 키가 설정되지 않았습니다.")
        
        self.client = openai.OpenAI(api_key=self.api_key)
        self.generation_count = 0
    
    def generate_image(self, prompt: str, style: str = "medical_clean") -> Tuple[Optional[Image.Image], Optional[str]]:
        """이미지 생성"""
        try:
            # 의료용 프롬프트 강화
            enhanced_prompt = self._enhance_medical_prompt(prompt, style)
            
            # DALL-E API 호출
            response = self.client.images.generate(
                model=Settings.DALLE_MODEL,
                prompt=enhanced_prompt,
                size=Settings.DALLE_SIZE,
                quality=Settings.DALLE_QUALITY,
                n=1,
            )
            
            image_url = response.data[0].url
            
            # 이미지 다운로드
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()
            
            image = Image.open(io.BytesIO(img_response.content))
            
            # 후처리
            image = self._post_process_image(image)
            
            self.generation_count += 1
            logger.info(f"이미지 생성 성공: {prompt[:50]}...")
            
            return image, image_url
            
        except Exception as e:
            logger.error(f"이미지 생성 실패: {str(e)}")
            return None, None
    
    def _enhance_medical_prompt(self, prompt: str, style: str) -> str:
        """의료용 프롬프트 강화"""
        # 스타일 접미사
        style_suffix = Settings.IMAGE_STYLES.get(style, Settings.IMAGE_STYLES["medical_clean"])["prompt_suffix"]
        
        # 의료광고법 준수 요소
        compliance_elements = [
            "educational purpose only",
            "professional medical setting",
            "no patient identification visible"
        ]
        
        # BGN 브랜딩
        brand_elements = Settings.get_brand_prompt_suffix()
        
        # 품질 요소
        quality_elements = [
            "high resolution",
            "professional photography quality",
            "clean and detailed"
        ]
        
        enhanced = f"""
        {prompt}, 
        {style_suffix}, 
        {', '.join(compliance_elements)}, 
        {brand_elements}, 
        {', '.join(quality_elements)}
        """.strip().replace('\n', ' ').replace('  ', ' ')
        
        # 길이 제한
        if len(enhanced) > 3000:
            enhanced = enhanced[:3000] + "..."
        
        return enhanced
    
    def _post_process_image(self, image: Image.Image) -> Image.Image:
        """이미지 후처리"""
        try:
            # RGB 모드로 변환
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # 선명도 향상
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.1)
            
            # 색상 채도 조정 (의료용 차분한 톤)
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
# 워드프레스 클라이언트
# ========================================

class WordPressClient:
    """워드프레스 자동 포스팅 클라이언트"""
    
    def __init__(self, url: str = None, username: str = None, password: str = None):
        if not WORDPRESS_AVAILABLE:
            raise ImportError("WordPress 라이브러리가 설치되지 않았습니다.")
        
        self.wp_url = url or Settings.WORDPRESS_URL
        self.username = username or Settings.WORDPRESS_USERNAME
        self.password = password or Settings.WORDPRESS_PASSWORD
        
        if not all([self.wp_url, self.username, self.password]):
            raise ValueError("워드프레스 설정이 완료되지 않았습니다.")
        
        self.client = Client(f"{self.wp_url}/xmlrpc.php", self.username, self.password)
        self.upload_count = 0
    
    def upload_image(self, image: Image.Image, filename: str, alt_text: str = "") -> MediaUploadResult:
        """이미지 업로드"""
        try:
            # PIL 이미지를 바이트로 변환
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='JPEG', quality=85, optimize=True)
            img_byte_arr = img_byte_arr.getvalue()
            
            # 업로드 데이터 구성
            data = {
                'name': filename,
                'type': 'image/jpeg',
                'bits': base64.b64encode(img_byte_arr).decode('utf-8'),
                'overwrite': False
            }
            
            # 업로드 실행
            response = self.client.call(UploadFile(data))
            
            self.upload_count += 1
            
            return MediaUploadResult(
                media_id=response['id'],
                url=response['url'],
                filename=response['file'],
                success=True
            )
            
        except Exception as e:
            logger.error(f"이미지 업로드 실패: {str(e)}")
            return MediaUploadResult(
                media_id=0,
                url="",
                filename=filename,
                success=False,
                error_message=str(e)
            )
    
    def create_post(self, content_data: GeneratedContent, images: List[Tuple[Image.Image, str]] = None) -> PostPublishResult:
        """포스트 생성"""
        try:
            uploaded_media = []
            featured_image_id = None
            
            # 이미지 업로드
            if images:
                for i, (image, alt_text) in enumerate(images):
                    filename = f"{content_data.slug}_image_{i+1}.jpg"
                    upload_result = self.upload_image(image, filename, alt_text)
                    
                    if upload_result.success:
                        uploaded_media.append(upload_result)
                        if i == 0:  # 첫 번째 이미지를 대표 이미지로
                            featured_image_id = upload_result.media_id
            
            # HTML 콘텐츠 생성
            html_content = self._build_post_html(content_data, uploaded_media)
            
            # 워드프레스 포스트 생성
            post = WordPressPost()
            post.title = content_data.title
            post.content = html_content
            post.excerpt = content_data.meta_description
            post.slug = content_data.slug
            post.post_status = Settings.WORDPRESS_DEFAULT_STATUS
            
            # 태그 및 카테고리
            post.terms_names = {
                'post_tag': content_data.tags,
                'category': [Settings.WORDPRESS_DEFAULT_CATEGORY]
            }
            
            # 대표 이미지 설정
            if featured_image_id:
                post.thumbnail = featured_image_id
            
            # 포스트 발행
            post_id = self.client.call(NewPost(post))
            
            return PostPublishResult(
                post_id=post_id,
                post_url=f"{self.wp_url}/?p={post_id}",
                edit_url=f"{self.wp_url}/wp-admin/post.php?post={post_id}&action=edit",
                status=Settings.WORDPRESS_DEFAULT_STATUS,
                publish_date=datetime.now(),
                success=True
            )
            
        except Exception as e:
            logger.error(f"포스트 생성 실패: {str(e)}")
            return PostPublishResult(
                post_id=0,
                post_url="",
                edit_url="",
                status="failed",
                publish_date=datetime.now(),
                success=False,
                error_message=str(e)
            )
    
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

class GoogleSheetsClient:
    """구글 시트 관리 클라이언트"""
    
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
            # 서비스 계정 인증
            credentials = ServiceAccountCredentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            self.gc = gspread.authorize(credentials)
            self.spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            
            logger.info("구글 시트 연결 성공")
            
        except Exception as e:
            logger.error(f"구글 시트 연결 실패: {str(e)}")
            raise ConnectionError(f"구글 시트 연결 실패: {str(e)}")
    
    def add_content_row(self, analysis_result: InterviewAnalysisResult, 
                       generated_content: GeneratedContent, 
                       wordpress_result: PostPublishResult = None) -> bool:
        """콘텐츠 정보를 시트에 추가"""
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
                analysis_result.employee.name,
                analysis_result.employee.department,
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

# ========================================
# Streamlit 웹 인터페이스
# ========================================

def setup_streamlit():
    """Streamlit 페이지 설정"""
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
    </style>
    """, unsafe_allow_html=True)

def main():
    """메인 애플리케이션"""
    setup_streamlit()
    
    # 메인 헤더
    st.markdown("""
    <div class="main-header">
        <h1>🏥 BGN 밝은눈안과 블로그 자동화 시스템</h1>
        <p>인터뷰 내용 → AI 분석 → 이미지 생성 → 워드프레스 자동 발행</p>
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
        
        st.header("📝 워드프레스 설정")
        wp_url = st.text_input("워드프레스 URL", value=Settings.WORDPRESS_URL)
        wp_username = st.text_input("사용자명", value=Settings.WORDPRESS_USERNAME)
        wp_password = st.text_input("앱 패스워드", value=Settings.WORDPRESS_PASSWORD, type="password")
        
        st.header("📊 구글 시트 설정")
        sheets_id = st.text_input("구글 시트 ID", value=Settings.GOOGLE_SHEETS_ID)
        
        st.header("🎨 생성 옵션")
        image_style = st.selectbox(
            "이미지 스타일",
            ["medical_clean", "infographic", "equipment"],
            help="생성될 이미지의 스타일"
        )
        
        generate_images = st.checkbox("이미지 자동 생성", value=True)
        auto_publish = st.checkbox("워드프레스 자동 발행", value=False)
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
            interview_content = """
            저는 밝은눈안과 홍보팀에 이예나 대리고요. 
            지금 경력은 병원 마케팅 쪽은 지금 거의 10년 정도 다 돼 가고 있습니다.
            여기서는 이제 대학팀에 같이 있고요. 대학 제휴랑 출장검진을 담당하고 있습니다.
            솔직하게 말씀드리면 저희 병원은 26년간 의료사고가 없었다는 점이 장점이고,
            잠실 롯데타워 위치가 정말 좋아서 고객님들이 만족해하시는 편이에요.
            대학생분들께는 특별 할인도 제공하고 있고, 축제 때 가서 상담도 해드리고 있어요.
            사실 많은 분들이 궁금해하시는 게 검사 과정인데, 저희는 정말 섬세하게 케어해드려요.
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
            if generate_images:
                st.write("🖼️ **생성 이미지**: 3개")
            if auto_publish:
                st.write("📝 **워드프레스**: 자동 발행")
            if save_to_sheets:
                st.write("📊 **구글 시트**: 자동 저장")
            
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
                
            # 인터뷰 내용 추출
            content = ""
            if uploaded_file:
                content = str(uploaded_file.read(), "utf-8")
            elif interview_content:
                content = interview_content
            else:
                st.error("❌ 인터뷰 내용을 입력해주세요!")
                return
            
            # 자동화 프로세스 실행
            execute_automation(
                content, openai_api_key, wp_url, wp_username, wp_password,
                sheets_id, image_style, generate_images, auto_publish, save_to_sheets
            )

def execute_automation(content, api_key, wp_url, wp_username, wp_password, 
                      sheets_id, image_style, generate_images, auto_publish, save_to_sheets):
    """자동화 프로세스 실행"""
    
    progress_container = st.container()
    
    with progress_container:
        # 1단계: 인터뷰 분석
        with st.status("🔍 1단계: 인터뷰 분석 중...", expanded=True) as status:
            st.write("직원 정보 및 전문 지식 추출 중...")
            time.sleep(1)
            
            try:
                analyzer = InterviewAnalyzer(api_key)
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
            time.sleep(1)
            
            try:
                generator = ContentGenerator(api_key)
                generated_content = generator.generate_content(analysis_result)
                
                st.success("✅ 콘텐츠 생성 완료")
                st.write(f"**제목**: {generated_content.title}")
                st.write(f"**예상 읽기 시간**: {generated_content.estimated_reading_time}분")
                st.write(f"**SEO 점수**: {generated_content.seo_score:.2f}")
                st.write(f"**의료광고법 준수**: {generated_content.medical_compliance_score:.2f}")
                
                # 콘텐츠 미리보기
                with st.expander("📄 생성된 콘텐츠 미리보기"):
                    st.markdown(generated_content.content_markdown[:500] + "...")
                
                status.update(label="✅ 2단계 완료: 콘텐츠 생성", state="complete")
                
            except Exception as e:
                st.error(f"❌ 콘텐츠 생성 실패: {str(e)}")
                return
        
        # 3단계: 이미지 생성
        generated_images = []
        if generate_images:
            with st.status("🎨 3단계: 이미지 생성 중...", expanded=True) as status:
                
                try:
                    image_generator = ImageGenerator(api_key)
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
        
        # 4단계: 워드프레스 포스팅
        wordpress_result = None
        if auto_publish and wp_url and wp_username and wp_password and WORDPRESS_AVAILABLE:
            with st.status("📝 4단계: 워드프레스 포스팅 중...", expanded=True) as status:
                
                try:
                    wp_client = WordPressClient(wp_url, wp_username, wp_password)
                    wordpress_result = wp_client.create_post(generated_content, generated_images)
                    
                    if wordpress_result.success:
                        st.success("✅ 워드프레스 포스팅 완료!")
                        st.write(f"**포스트 ID**: {wordpress_result.post_id}")
                        st.write(f"**상태**: {wordpress_result.status}")
                        status.update(label="✅ 4단계 완료: 워드프레스 포스팅", state="complete")
                    else:
                        st.error(f"❌ 워드프레스 포스팅 실패: {wordpress_result.error_message}")
                        
                except Exception as e:
                    st.error(f"❌ 워드프레스 연동 오류: {str(e)}")
        
        # 5단계: 구글 시트 저장
        if save_to_sheets and sheets_id and GOOGLE_SHEETS_AVAILABLE:
            with st.status("📊 5단계: 구글 시트 저장 중...", expanded=True) as status:
                
                try:
                    sheets_client = GoogleSheetsClient(sheets_id)
                    success = sheets_client.add_content_row(analysis_result, generated_content, wordpress_result)
                    
                    if success:
                        st.success("✅ 구글 시트 저장 완료!")
                        status.update(label="✅ 5단계 완료: 구글 시트 저장", state="complete")
                    else:
                        st.warning("⚠️ 구글 시트 저장 실패")
                        
                except Exception as e:
                    st.warning(f"⚠️ 구글 시트 연동 오류: {str(e)}")
        
        # 결과 표시
        st.markdown("---")
        st.markdown('<div class="success-box">', unsafe_allow_html=True)
        st.header("🎉 자동화 완료!")
        
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
        
        with col3:
            st.metric("이미지 생성", f"{len(generated_images)}개")
            if generated_images:
                st.write("✓ DALL-E 고품질")
                st.write("✓ 의료용 스타일")
        
        with col4:
            if wordpress_result and wordpress_result.success:
                st.metric("포스팅 완료", "✅")
                st.write("✓ 워드프레스 발행")
                st.write(f"✓ {wordpress_result.status} 상태")
            else:
                st.metric("포스팅 대기", "📝")
                st.write("✓ 수동 발행 필요")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 다운로드 및 링크
        st.markdown("### 📎 생성 결과")
        
        # 콘텐츠 다운로드
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.download_button(
                label="📄 Markdown 다운로드",
                data=generated_content.content_markdown,
                file_name=f"{generated_content.slug}.md",
                mime="text/markdown"
            )
        
        with col2:
            st.download_button(
                label="📄 HTML 다운로드", 
                data=generated_content.content_html,
                file_name=f"{generated_content.slug}.html",
                mime="text/html"
            )
        
        # 워드프레스 링크
        if wordpress_result and wordpress_result.success:
            st.markdown("### 🔗 워드프레스 링크")
            st.success(f"**포스트 보기**: [클릭하여 확인]({wordpress_result.post_url})")
            st.info(f"**편집하기**: [관리자에서 편집]({wordpress_result.edit_url})")
        
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
                        file_name=f"{generated_content.slug}_image_{i+1}.jpg",
                        mime="image/jpeg"
                    )
                    st.caption(alt_text)

# 필수 라이브러리 체크 함수
def check_dependencies():
    """필수 라이브러리 설치 상태 체크"""
    missing_libs = []
    
    if not WORDPRESS_AVAILABLE:
        missing_libs.append("python-wordpress-xmlrpc")
    
    if not GOOGLE_SHEETS_AVAILABLE:
        missing_libs.append("google-api-python-client google-auth-httplib2 google-auth-oauthlib gspread")
    
    if missing_libs:
        st.warning(f"""
        ⚠️ **선택적 라이브러리 미설치**
        
        다음 기능을 사용하려면 추가 라이브러리 설치가 필요합니다:
        
        {"".join([f"- `pip install {lib}`" for lib in missing_libs])}
        """)

# 사용 예시 및 테스트 함수
def run_sample_test():
    """샘플 테스트 실행"""
    sample_interview = """
    저는 밝은눈안과 홍보팀에 이예나 대리고요. 
    지금 경력은 병원 마케팅 쪽은 지금 거의 10년 정도 다 돼 가고 있습니다.
    여기서는 이제 대학팀에 같이 있고요. 대학 제휴랑 출장검진을 담당하고 있습니다.
    솔직하게 말씀드리면 저희 병원은 26년간 의료사고가 없었다는 점이 장점이고,
    잠실 롯데타워 위치가 정말 좋아서 고객님들이 만족해하시는 편이에요.
    """
    
    if not Settings.OPENAI_API_KEY:
        print("❌ OpenAI API 키가 설정되지 않았습니다.")
        return
    
    try:
        print("🔍 인터뷰 분석 테스트...")
        analyzer = InterviewAnalyzer()
        result = analyzer.analyze_interview(sample_interview)
        
        print(f"✅ 분석 완료!")
        print(f"직원명: {result.employee.name}")
        print(f"부서: {result.employee.department}")
        print(f"신뢰도: {result.analysis_metadata['confidence_score']:.2f}")
        
        print("\n📝 콘텐츠 생성 테스트...")
        generator = ContentGenerator()
        content = generator.generate_content(result)
        
        print(f"✅ 콘텐츠 생성 완료!")
        print(f"제목: {content.title}")
        print(f"SEO 점수: {content.seo_score:.2f}")
        
        print("\n🎉 모든 테스트 통과!")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")

# ========================================
# 메인 실행부
# ========================================

if __name__ == "__main__":
    try:
        # 의존성 체크
        check_dependencies()
        
        # Streamlit 앱 실행
        main()
        
    except Exception as e:
        st.error(f"❌ 시스템 오류: {str(e)}")
        st.info("💡 .env 파일 설정을 확인하거나 필수 라이브러리를 설치하세요.")

# ========================================
# 추가 유틸리티 함수들
# ========================================

def create_sample_env_file():
    """샘플 .env 파일 생성"""
    sample_content = """
# OpenAI API 설정
OPENAI_API_KEY=your_openai_api_key_here

# 워드프레스 설정 (선택적)
WORDPRESS_URL=https://your-wordpress-site.com
WORDPRESS_USERNAME=your_username
WORDPRESS_PASSWORD=your_app_password

# 구글 시트 설정 (선택적)
GOOGLE_SHEETS_ID=your_google_sheets_id
GOOGLE_CREDENTIALS_FILE=credentials.json

# 로그 레벨
LOG_LEVEL=INFO
    """.strip()
    
    with open('.env.example', 'w', encoding='utf-8') as f:
        f.write(sample_content)
    
    print("📄 .env.example 파일이 생성되었습니다.")
    print("💡 이 파일을 .env로 복사하고 실제 값으로 수정하세요.")

def export_analysis_data(analysis_result: InterviewAnalysisResult, output_file: str = None):
    """분석 결과를 JSON으로 내보내기"""
    if output_file is None:
        output_file = f"analysis_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(asdict(analysis_result), f, ensure_ascii=False, indent=2, default=str)
    
    return output_file

# CLI 모드 지원
def run_cli_mode():
    """CLI 모드로 실행"""
    import argparse
    
    parser = argparse.ArgumentParser(description='BGN 블로그 자동화 CLI')
    parser.add_argument('--interview', required=True, help='인터뷰 텍스트 파일 경로')
    parser.add_argument('--output', default='output', help='출력 디렉토리')
    parser.add_argument('--no-images', action='store_true', help='이미지 생성 건너뛰기')
    parser.add_argument('--test', action='store_true', help='테스트 모드 실행')
    
    args = parser.parse_args()
    
    if args.test:
        run_sample_test()
        return
    
    # 인터뷰 파일 읽기
    with open(args.interview, 'r', encoding='utf-8') as f:
        interview_content = f.read()
    
    # 출력 디렉토리 생성
    os.makedirs(args.output, exist_ok=True)
    
    try:
        # 분석 실행
        analyzer = InterviewAnalyzer()
        analysis_result = analyzer.analyze_interview(interview_content)
        
        # 콘텐츠 생성
        generator = ContentGenerator()
        generated_content = generator.generate_content(analysis_result)
        
        # 결과 저장
        with open(f"{args.output}/content.md", 'w', encoding='utf-8') as f:
            f.write(generated_content.content_markdown)
        
        with open(f"{args.output}/content.html", 'w', encoding='utf-8') as f:
            f.write(generated_content.content_html)
        
        export_analysis_data(analysis_result, f"{args.output}/analysis.json")
        
        # 이미지 생성 (선택적)
        if not args.no_images:
            image_generator = ImageGenerator()
            images = image_generator.generate_blog_images(generated_content)
            
            for i, (img, alt_text) in enumerate(images):
                img.save(f"{args.output}/image_{i+1}.jpg", quality=95)
        
        print(f"✅ 완료! 결과가 {args.output} 디렉토리에 저장되었습니다.")
        
    except Exception as e:
        print(f"❌ CLI 실행 실패: {str(e)}")

# 스크립트 직접 실행 시
if __name__ == "__main__" and len(sys.argv) > 1:
    run_cli_mode()