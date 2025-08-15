#!/usr/bin/env python3
"""
src/analyzers/interview_analyzer.py

📋 역할: 직원 인터뷰 내용을 분석하여 블로그 콘텐츠 생성을 위한 데이터 추출
- 인터뷰 텍스트에서 직원 정보 (이름, 직책, 경력, 전문분야) 자동 추출
- 개인별 말투, 어투, 성격 특성 분석
- 전문 지식 및 업무 노하우 식별
- 고객 관련 인사이트 (자주 받는 질문, 피드백) 추출
- 병원 강점 및 차별화 포인트 발굴
- 의료광고법 준수를 위한 표현 검증
- 콘텐츠 생성을 위한 구조화된 데이터 출력
"""

import openai
import re
import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import logging
from dataclasses import dataclass, asdict
import os
import sys

# 프로젝트 내부 모듈
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config.settings import Settings

# 로깅 설정
logging.basicConfig(level=getattr(logging, Settings.LOG_LEVEL))
logger = logging.getLogger(__name__)

@dataclass
class EmployeeProfile:
    """직원 프로필 데이터 클래스"""
    name: str = ""
    position: str = ""
    department: str = ""
    experience_years: int = 0
    career_history: List[str] = None
    specialty_areas: List[str] = None
    
    def __post_init__(self):
        if self.career_history is None:
            self.career_history = []
        if self.specialty_areas is None:
            self.specialty_areas = []

@dataclass
class PersonalityTraits:
    """개성/말투 특성 데이터 클래스"""
    tone_style: str = ""  # 솔직함, 전문적, 친근함 등
    frequent_expressions: List[str] = None  # 자주 쓰는 표현
    communication_style: str = ""  # 설명 방식의 특징
    personality_keywords: List[str] = None  # 성격을 나타내는 키워드
    formality_level: str = ""  # 격식 수준 (formal, casual, mixed)
    
    def __post_init__(self):
        if self.frequent_expressions is None:
            self.frequent_expressions = []
        if self.personality_keywords is None:
            self.personality_keywords = []

@dataclass
class ProfessionalKnowledge:
    """전문 지식 데이터 클래스"""
    procedures: List[str] = None  # 담당 시술/검사
    equipment: List[str] = None  # 사용 장비
    processes: List[str] = None  # 업무 프로세스
    technical_terms: List[str] = None  # 전문 용어
    expertise_level: str = ""  # 전문성 수준
    
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
    """고객 관련 인사이트 데이터 클래스"""
    frequent_questions: List[str] = None  # 자주 받는 질문
    customer_feedback: List[str] = None  # 고객 피드백
    pain_points: List[str] = None  # 고객 고민사항
    success_stories: List[str] = None  # 성공 사례 (개인정보 제외)
    target_demographics: List[str] = None  # 주요 고객층
    
    def __post_init__(self):
        if self.frequent_questions is None:
            self.frequent_questions = []
        if self.customer_feedback is None:
            self.customer_feedback = []
        if self.pain_points is None:
            self.pain_points = []
        if self.success_stories is None:
            self.success_stories = []
        if self.target_demographics is None:
            self.target_demographics = []

@dataclass
class HospitalStrengths:
    """병원 강점 데이터 클래스"""
    competitive_advantages: List[str] = None  # 경쟁 우위
    unique_services: List[str] = None  # 특별 서비스
    equipment_advantages: List[str] = None  # 장비 우위
    location_benefits: List[str] = None  # 위치상 장점
    team_strengths: List[str] = None  # 팀/인력 강점
    
    def __post_init__(self):
        if self.competitive_advantages is None:
            self.competitive_advantages = []
        if self.unique_services is None:
            self.unique_services = []
        if self.equipment_advantages is None:
            self.equipment_advantages = []
        if self.location_benefits is None:
            self.location_benefits = []
        if self.team_strengths is None:
            self.team_strengths = []

@dataclass
class InterviewAnalysisResult:
    """인터뷰 분석 종합 결과"""
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
                "content_length": 0,
                "medical_compliance_checked": False
            }

class BGNInterviewAnalyzer:
    """BGN 직원 인터뷰 분석기"""
    
    def __init__(self, api_key: str = None):
        """
        인터뷰 분석기 초기화
        
        Args:
            api_key: OpenAI API 키 (None인 경우 settings에서 가져옴)
        """
        self.api_key = api_key or Settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API 키가 설정되지 않았습니다.")
        
        self.client = openai.OpenAI(api_key=self.api_key)
        self.analysis_count = 0
        
        # 분석 패턴 정의
        self._setup_analysis_patterns()
        
        logger.info("BGN 인터뷰 분석기가 초기화되었습니다.")
    
    def _setup_analysis_patterns(self):
        """분석에 사용할 패턴들 설정"""
        
        # 직책 패턴
        self.position_patterns = {
            r'(홍보|마케팅).*?(팀|부).*?(대리|과장|팀장|부장)': '홍보팀',
            r'(상담|접수).*?(팀|부).*?(대리|과장|팀장)': '상담팀',
            r'(검안|검사).*?(팀|부|사).*?(대리|과장|검안사)': '검안팀',
            r'(간호|케어).*?(팀|부|사).*?(대리|과장|간호사)': '간호팀',
            r'(원장|의사|닥터)': '의료진'
        }
        
        # 경력 추출 패턴
        self.experience_patterns = [
            r'(\d+)년\s*(정도|차|째|경력)',
            r'경력.*?(\d+)년',
            r'(\d+)년.*?(일|근무|경험)'
        ]
        
        # 말투 분석 키워드
        self.personality_markers = {
            '솔직함': ['솔직하게', '사실', '정말로', '진짜'],
            '현실적': ['실제로', '경험상', '보통은', '일반적으로'],
            '배려심': ['걱정하지 마시고', '편하게', '천천히', '괜찮아요'],
            '전문성': ['의료진과', '정확한', '전문적으로', '임상적으로'],
            '친근함': ['~해요', '~거든요', '~네요', '같아서'],
            '겸손함': ['제가 알기로는', '아마도', '~인 것 같아요']
        }
        
        # 전문 용어 패턴
        self.medical_terms = [
            '스마일라식', '라식', '라섹', '백내장', '녹내장', '망막',
            '각막', '시력교정', '검안', '안압', '시야검사', 'OCT',
            '안저검사', '각막지형도', '눈물층', '마이봄샘', '건성안',
            '비문증', '황반변성', '당뇨망막병증', '자가혈청안약'
        ]
    
    def analyze_interview(self, 
                         interview_text: str, 
                         use_ai_enhancement: bool = True) -> InterviewAnalysisResult:
        """
        인터뷰 텍스트 종합 분석
        
        Args:
            interview_text: 인터뷰 원문
            use_ai_enhancement: AI 기반 고급 분석 사용 여부
            
        Returns:
            InterviewAnalysisResult: 분석 결과
        """
        logger.info(f"인터뷰 분석 시작 (길이: {len(interview_text)}자)")
        
        # 기본 전처리
        cleaned_text = self._preprocess_text(interview_text)
        
        # 기본 패턴 기반 분석
        employee = self._extract_employee_info(cleaned_text)
        personality = self._analyze_personality(cleaned_text)
        knowledge = self._extract_professional_knowledge(cleaned_text)
        customer_insights = self._extract_customer_insights(cleaned_text)
        hospital_strengths = self._extract_hospital_strengths(cleaned_text)
        
        # AI 기반 고급 분석 (선택적)
        if use_ai_enhancement and self.api_key:
            try:
                ai_analysis = self._ai_enhanced_analysis(cleaned_text)
                employee, personality, knowledge, customer_insights, hospital_strengths = \
                    self._merge_analysis_results(
                        (employee, personality, knowledge, customer_insights, hospital_strengths),
                        ai_analysis
                    )
            except Exception as e:
                logger.warning(f"AI 분석 실패, 기본 분석 결과 사용: {str(e)}")
        
        # 의료광고법 검증
        compliance_check = self._check_medical_compliance(cleaned_text)
        
        # 메타데이터 생성
        metadata = {
            "analysis_date": datetime.now().isoformat(),
            "confidence_score": self._calculate_confidence_score(employee, personality, knowledge),
            "content_length": len(cleaned_text),
            "medical_compliance_checked": compliance_check,
            "ai_enhancement_used": use_ai_enhancement
        }
        
        # 결과 조합
        result = InterviewAnalysisResult(
            employee=employee,
            personality=personality,
            knowledge=knowledge,
            customer_insights=customer_insights,
            hospital_strengths=hospital_strengths,
            analysis_metadata=metadata
        )
        
        self.analysis_count += 1
        logger.info(f"인터뷰 분석 완료 (신뢰도: {metadata['confidence_score']:.2f})")
        
        return result
    
    def _preprocess_text(self, text: str) -> str:
        """텍스트 전처리"""
        # 줄바꿈 정리
        text = re.sub(r'\n+', '\n', text)
        
        # 불필요한 공백 제거
        text = re.sub(r'\s+', ' ', text)
        
        # 타임스탬프 제거 (00:00 형태)
        text = re.sub(r'\d{2}:\d{2}', '', text)
        
        # 참석자 번호 제거 (참석자 1, 참석자 2 등)
        text = re.sub(r'참석자\s*\d+\s*', '', text)
        
        return text.strip()
    
    def _extract_employee_info(self, text: str) -> EmployeeProfile:
        """직원 기본 정보 추출"""
        employee = EmployeeProfile()
        
        # 이름 추출 (간단한 패턴)
        name_patterns = [
            r'저는\s*([가-힣]{2,4})\s*(대리|과장|팀장|부장)',
            r'([가-힣]{2,4})\s*(대리|과장|팀장|부장).*?입니다',
            r'홍보.*?([가-힣]{2,4})'
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text)
            if match:
                employee.name = match.group(1)
                break
        
        # 직책 추출
        for pattern, dept in self.position_patterns.items():
            if re.search(pattern, text):
                employee.department = dept
                # 직급 추출
                position_match = re.search(r'(대리|과장|팀장|부장|원장)', text)
                if position_match:
                    employee.position = position_match.group(1)
                break
        
        # 경력 추출
        for pattern in self.experience_patterns:
            match = re.search(pattern, text)
            if match:
                employee.experience_years = int(match.group(1))
                break
        
        # 전문분야 추출
        if '대학' in text and '제휴' in text:
            employee.specialty_areas.append('대학 제휴')
        if '출장' in text and '검진' in text:
            employee.specialty_areas.append('출장검진')
        if '축제' in text:
            employee.specialty_areas.append('축제 마케팅')
        if '상담' in text:
            employee.specialty_areas.append('고객 상담')
        
        return employee
    
    def _analyze_personality(self, text: str) -> PersonalityTraits:
        """개성 및 말투 분석"""
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
        
        # 자주 쓰는 표현 추출
        frequent_phrases = []
        for markers in self.personality_markers.values():
            for marker in markers:
                if text.count(marker) >= 2:  # 2번 이상 등장
                    frequent_phrases.append(marker)
        
        personality.frequent_expressions = frequent_phrases
        
        # 격식 수준 판단
        formal_markers = ['습니다', '됩니다', '드립니다']
        casual_markers = ['해요', '거든요', '네요', '인데']
        
        formal_count = sum(text.count(marker) for marker in formal_markers)
        casual_count = sum(text.count(marker) for marker in casual_markers)
        
        if formal_count > casual_count * 1.5:
            personality.formality_level = 'formal'
        elif casual_count > formal_count * 1.5:
            personality.formality_level = 'casual'
        else:
            personality.formality_level = 'mixed'
        
        # 소통 스타일 분석
        if '경험' in text and '실제' in text:
            personality.communication_style = '경험 중심'
        elif '예를 들어' in text or '예시' in text:
            personality.communication_style = '예시 중심'
        elif '데이터' in text or '통계' in text:
            personality.communication_style = '데이터 중심'
        else:
            personality.communication_style = '일반적'
        
        return personality
    
    def _extract_professional_knowledge(self, text: str) -> ProfessionalKnowledge:
        """전문 지식 추출"""
        knowledge = ProfessionalKnowledge()
        
        # 의료 시술/검사 추출
        for term in self.medical_terms:
            if term in text:
                if '검사' in term or 'OCT' in term or '시야' in term:
                    knowledge.procedures.append(term)
                elif '라식' in term or '수술' in term:
                    knowledge.procedures.append(term)
                else:
                    knowledge.technical_terms.append(term)
        
        # 장비 추출
        equipment_keywords = ['비즈맥스', '장비', '기계', '검사기', '레이저']
        for keyword in equipment_keywords:
            if keyword in text:
                # 주변 문맥에서 구체적인 장비명 추출 시도
                equipment_match = re.search(f'{keyword}[^.]*', text)
                if equipment_match:
                    knowledge.equipment.append(equipment_match.group())
        
        # 업무 프로세스 추출
        process_keywords = ['접수', '검안', '진료', '상담', '출장검진', '축제']
        for keyword in process_keywords:
            if keyword in text:
                knowledge.processes.append(keyword)
        
        # 전문성 수준 평가
        expertise_indicators = len(knowledge.procedures) + len(knowledge.technical_terms)
        if expertise_indicators >= 5:
            knowledge.expertise_level = '전문가'
        elif expertise_indicators >= 3:
            knowledge.expertise_level = '숙련자'
        elif expertise_indicators >= 1:
            knowledge.expertise_level = '경험자'
        else:
            knowledge.expertise_level = '일반'
        
        return knowledge
    
    def _extract_customer_insights(self, text: str) -> CustomerInsights:
        """고객 관련 인사이트 추출"""
        insights = CustomerInsights()
        
        # 자주 받는 질문 패턴 추출
        question_patterns = [
            r'자주\s*[물어|받는|하는].*?질문',
            r'많이\s*[물어|받는|하는].*?질문',
            r'궁금해.*?하[시는|는]',
            r'문의.*?많[이|은]'
        ]
        
        for pattern in question_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                # 질문 내용 추출 (간단한 휴리스틱)
                context = text[max(0, match.start()-50):match.end()+100]
                insights.frequent_questions.append(context.strip())
        
        # 고객 피드백 추출
        feedback_patterns = [
            r'(좋다|만족|감사|고맙다).*?[고하]',
            r'(섬세|친절|정확).*?[다고|하]',
            r'추천.*?[하는|받는]'
        ]
        
        for pattern in feedback_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                context = text[max(0, match.start()-30):match.end()+50]
                insights.customer_feedback.append(context.strip())
        
        # 타겟 고객층 추출
        if '대학생' in text:
            insights.target_demographics.append('대학생')
        if '직장인' in text or '회사' in text:
            insights.target_demographics.append('직장인')
        if '어르신' in text or '노인' in text:
            insights.target_demographics.append('중장년층')
        if '군인' in text or '군부대' in text:
            insights.target_demographics.append('군인')
        
        return insights
    
    def _extract_hospital_strengths(self, text: str) -> HospitalStrengths:
        """병원 강점 추출"""
        strengths = HospitalStrengths()
        
        # 위치 장점
        location_keywords = ['롯데타워', '잠실', '위치', '접근성', '교통']
        for keyword in location_keywords:
            if keyword in text:
                strengths.location_benefits.append(f'{keyword} 관련 장점')
        
        # 장비 우위
        equipment_advantages = ['최신', '정밀', '고급', '첨단', '많은 장비']
        for advantage in equipment_advantages:
            if advantage in text and ('장비' in text or '기계' in text):
                strengths.equipment_advantages.append(f'{advantage} 장비')
        
        # 서비스 차별점
        if '개인별' in text and ('케어' in text or '관리' in text):
            strengths.unique_services.append('개인별 맞춤 케어')
        
        if '무사고' in text or '사고' in text:
            strengths.competitive_advantages.append('안전한 시술 기록')
        
        if '갤러리' in text:
            strengths.unique_services.append('갤러리 운영')
        
        # 팀 강점
        teamwork_indicators = ['팀워크', '협력', '소통', '친절']
        for indicator in teamwork_indicators:
            if indicator in text:
                strengths.team_strengths.append(f'{indicator} 우수')
        
        return strengths
    
    def _ai_enhanced_analysis(self, text: str) -> Dict:
        """AI 기반 고급 분석"""
        try:
            analysis_prompt = f"""
            다음은 BGN 밝은눈안과 직원 인터뷰입니다. 이를 분석하여 JSON 형태로 정보를 추출해주세요.

            인터뷰 내용:
            {text[:3000]}  # 토큰 제한 고려

            다음 형식으로 분석 결과를 JSON으로 제공해주세요:
            {{
                "employee": {{
                    "name": "추출된 이름",
                    "position": "직책",
                    "department": "부서",
                    "experience_years": 경력년수,
                    "specialty_areas": ["전문분야1", "전문분야2"]
                }},
                "personality": {{
                    "tone_style": "말투 특성",
                    "frequent_expressions": ["자주 쓰는 표현들"],
                    "communication_style": "소통 방식",
                    "personality_keywords": ["성격 키워드들"]
                }},
                "customer_insights": {{
                    "frequent_questions": ["자주 받는 질문들"],
                    "customer_feedback": ["고객 피드백들"],
                    "target_demographics": ["주요 고객층들"]
                }},
                "hospital_strengths": {{
                    "competitive_advantages": ["경쟁 우위들"],
                    "unique_services": ["특별 서비스들"]
                }}
            }}

            의료광고법을 준수하여 과장된 표현은 제외하고 분석해주세요.
            """
            
            response = self.client.chat.completions.create(
                model=Settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "당신은 의료 업계 인사 분석 전문가입니다. 정확하고 객관적인 분석을 제공해주세요."},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=Settings.OPENAI_TEMPERATURE,
                max_tokens=Settings.OPENAI_MAX_TOKENS
            )
            
            ai_result = response.choices[0].message.content
            
            # JSON 파싱 시도
            try:
                return json.loads(ai_result)
            except json.JSONDecodeError:
                # JSON이 아닌 경우 간단한 파싱 시도
                logger.warning("AI 응답이 유효한 JSON이 아닙니다.")
                return {}
                
        except Exception as e:
            logger.error(f"AI 분석 실패: {str(e)}")
            return {}
    
    def _merge_analysis_results(self, basic_results: Tuple, ai_results: Dict) -> Tuple:
        """기본 분석과 AI 분석 결과 병합"""
        employee, personality, knowledge, customer_insights, hospital_strengths = basic_results
        
        if not ai_results:
            return basic_results
        
        try:
            # AI 결과로 기본 결과 보강
            if 'employee' in ai_results:
                ai_emp = ai_results['employee']
                if ai_emp.get('name') and not employee.name:
                    employee.name = ai_emp['name']
                if ai_emp.get('specialty_areas'):
                    employee.specialty_areas.extend(ai_emp['specialty_areas'])
            
            if 'personality' in ai_results:
                ai_pers = ai_results['personality']
                if ai_pers.get('frequent_expressions'):
                    personality.frequent_expressions.extend(ai_pers['frequent_expressions'])
            
            # 중복 제거
            employee.specialty_areas = list(set(employee.specialty_areas))
            personality.frequent_expressions = list(set(personality.frequent_expressions))
            
        except Exception as e:
            logger.warning(f"결과 병합 중 오류: {str(e)}")
        
        return employee, personality, knowledge, customer_insights, hospital_strengths
    
    def _check_medical_compliance(self, text: str) -> bool:
        """의료광고법 준수 여부 검사"""
        violations = []
        
        for keyword in Settings.PROHIBITED_KEYWORDS:
            if keyword in text:
                violations.append(keyword)
        
        if violations:
            logger.warning(f"의료광고법 위반 가능 키워드 발견: {violations}")
            return False
        
        return True
    
    def _calculate_confidence_score(self, 
                                  employee: EmployeeProfile, 
                                  personality: PersonalityTraits, 
                                  knowledge: ProfessionalKnowledge) -> float:
        """분석 결과 신뢰도 점수 계산"""
        score = 0.0
        
        # 직원 정보 완성도
        if employee.name:
            score += 0.2
        if employee.position:
            score += 0.15
        if employee.experience_years > 0:
            score += 0.15
        if employee.specialty_areas:
            score += 0.1
        
        # 개성 분석 완성도
        if personality.tone_style:
            score += 0.15
        if personality.frequent_expressions:
            score += 0.1
        
        # 전문 지식 완성도
        if knowledge.procedures:
            score += 0.1
        if knowledge.technical_terms:
            score += 0.05
        
        return min(score, 1.0)
    
    def generate_content_recommendations(self, 
                                       analysis_result: InterviewAnalysisResult) -> Dict[str, List[str]]:
        """분석 결과를 바탕으로 콘텐츠 추천"""
        recommendations = {
            "suggested_topics": [],
            "target_keywords": [],
            "content_angles": [],
            "tone_guidelines": []
        }
        
        # 전문분야 기반 토픽 추천
        for specialty in analysis_result.employee.specialty_areas:
            if '대학' in specialty:
                recommendations["suggested_topics"].extend([
                    "대학생 시력교정 가이드",
                    "방학 시즌 수술 준비",
                    "학생 할인 혜택 안내"
                ])
            elif '출장' in specialty:
                recommendations["suggested_topics"].extend([
                    "기업 출장검진 프로세스",
                    "직장인 눈 건강 관리",
                    "정밀 안과검사 안내"
                ])
        
        # 개성 기반 톤 가이드라인
        personality = analysis_result.personality
        if personality.tone_style == '솔직함':
            recommendations["tone_guidelines"].append("현실적이고 솔직한 어투 사용")
        if personality.tone_style == '배려심':
            recommendations["tone_guidelines"].append("따뜻하고 배려 있는 표현 활용")
        if personality.tone_style == '전문성':
            recommendations["tone_guidelines"].append("전문적이지만 이해하기 쉬운 설명")
        
        # 자주 쓰는 표현 반영
        if personality.frequent_expressions:
            recommendations["tone_guidelines"].append(
                f"특징 표현 활용: {', '.join(personality.frequent_expressions[:3])}"
            )
        
        # 고객 인사이트 기반 키워드
        for question in analysis_result.customer_insights.frequent_questions:
            if '할인' in question:
                recommendations["target_keywords"].append("학생 할인")
            if '검사' in question:
                recommendations["target_keywords"].append("정밀 검사")
            if '수술' in question:
                recommendations["target_keywords"].append("시력교정수술")
        
        # 병원 강점 기반 콘텐츠 앵글
        for advantage in analysis_result.hospital_strengths.competitive_advantages:
            if '위치' in advantage or '롯데타워' in advantage:
                recommendations["content_angles"].append("접근성과 편의성 강조")
            if '무사고' in advantage:
                recommendations["content_angles"].append("안전성과 신뢰성 중점")
        
        return recommendations
    
    def export_analysis_result(self, 
                             result: InterviewAnalysisResult, 
                             format: str = "json") -> str:
        """분석 결과를 지정된 형식으로 내보내기"""
        
        if format.lower() == "json":
            return json.dumps(asdict(result), ensure_ascii=False, indent=2)
        
        elif format.lower() == "summary":
            return self._generate_analysis_summary(result)
        
        elif format.lower() == "content_brief":
            return self._generate_content_brief(result)
        
        else:
            raise ValueError(f"지원하지 않는 형식: {format}")
    
    def _generate_analysis_summary(self, result: InterviewAnalysisResult) -> str:
        """분석 결과 요약 생성"""
        summary = f"""
BGN 직원 인터뷰 분석 요약

=== 직원 정보 ===
이름: {result.employee.name or '미상'}
직책: {result.employee.position or '미상'}
부서: {result.employee.department or '미상'}
경력: {result.employee.experience_years}년
전문분야: {', '.join(result.employee.specialty_areas) or '없음'}

=== 개성 분석 ===
말투 스타일: {result.personality.tone_style or '일반적'}
소통 방식: {result.personality.communication_style or '일반적'}
격식 수준: {result.personality.formality_level or '혼합'}
자주 쓰는 표현: {', '.join(result.personality.frequent_expressions[:5]) or '없음'}

=== 전문 지식 ===
담당 시술: {', '.join(result.knowledge.procedures[:5]) or '없음'}
사용 장비: {', '.join(result.knowledge.equipment[:3]) or '없음'}
전문성 수준: {result.knowledge.expertise_level or '일반'}

=== 고객 인사이트 ===
주요 고객층: {', '.join(result.customer_insights.target_demographics) or '없음'}
자주 받는 질문 수: {len(result.customer_insights.frequent_questions)}개

=== 병원 강점 ===
경쟁 우위: {', '.join(result.hospital_strengths.competitive_advantages) or '없음'}
특별 서비스: {', '.join(result.hospital_strengths.unique_services) or '없음'}

=== 분석 메타데이터 ===
신뢰도 점수: {result.analysis_metadata.get('confidence_score', 0):.2f}
의료광고법 준수: {'✓' if result.analysis_metadata.get('medical_compliance_checked', False) else '✗'}
분석 일시: {result.analysis_metadata.get('analysis_date', '미상')}
        """.strip()
        
        return summary
    
    def _generate_content_brief(self, result: InterviewAnalysisResult) -> str:
        """콘텐츠 제작을 위한 브리프 생성"""
        
        recommendations = self.generate_content_recommendations(result)
        
        brief = f"""
BGN 블로그 콘텐츠 제작 브리프

=== 작성자 프로필 ===
담당자: {result.employee.name} {result.employee.position}
전문분야: {', '.join(result.employee.specialty_areas)}
경력: {result.employee.experience_years}년

=== 톤앤매너 가이드라인 ===
{chr(10).join('• ' + guideline for guideline in recommendations['tone_guidelines'])}

=== 추천 콘텐츠 주제 ===
{chr(10).join('• ' + topic for topic in recommendations['suggested_topics'])}

=== 타겟 키워드 ===
{', '.join(recommendations['target_keywords'])}

=== 콘텐츠 앵글 ===
{chr(10).join('• ' + angle for angle in recommendations['content_angles'])}

=== 활용 가능한 인사이트 ===
고객 질문: {len(result.customer_insights.frequent_questions)}개 확보
고객 피드백: {len(result.customer_insights.customer_feedback)}개 확보
병원 강점: {len(result.hospital_strengths.competitive_advantages + result.hospital_strengths.unique_services)}개 확보

=== 의료광고법 준수 사항 ===
• 효과 보장 표현 금지
• 비교 우월 표현 금지  
• 가격 언급 금지
• 과도한 시술 상세 설명 금지
        """.strip()
        
        return brief

# 유틸리티 함수들
def quick_analyze(interview_text: str, api_key: str = None) -> Dict:
    """빠른 인터뷰 분석 (간단한 사용을 위한 함수)"""
    analyzer = BGNInterviewAnalyzer(api_key)
    result = analyzer.analyze_interview(interview_text, use_ai_enhancement=False)
    return asdict(result)

def batch_analyze_interviews(interview_files: List[str], 
                           output_dir: str = "data/analysis_results") -> List[Dict]:
    """여러 인터뷰 파일 일괄 분석"""
    analyzer = BGNInterviewAnalyzer()
    results = []
    
    os.makedirs(output_dir, exist_ok=True)
    
    for file_path in interview_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            result = analyzer.analyze_interview(content)
            results.append(asdict(result))
            
            # 개별 결과 저장
            filename = os.path.basename(file_path).replace('.txt', '_analysis.json')
            output_path = os.path.join(output_dir, filename)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(result), f, ensure_ascii=False, indent=2)
            
            logger.info(f"분석 완료: {file_path} -> {output_path}")
            
        except Exception as e:
            logger.error(f"파일 분석 실패 {file_path}: {str(e)}")
    
    return results

# 사용 예시 및 테스트
if __name__ == "__main__":
    # 테스트용 샘플 인터뷰
    sample_interview = """
    저는 밝은눈안과 홍보팀에 이예나 대리고요. 
    지금 경력은 병원 마케팅 쪽은 지금 거의 10년 정도 다 돼 가고 있습니다.
    여기서는 이제 대학팀에 같이 있고요. 대학 제휴랑 출장검진을 담당하고 있습니다.
    솔직하게 말씀드리면 저희 병원은 26년간 의료사고가 없었다는 점이 장점이고,
    잠실 롯데타워 위치가 정말 좋아서 고객님들이 만족해하시는 편이에요.
    대학생분들한테는 특별 할인도 제공하고 있고, 축제 때 가서 상담도 해드리고 있어요.
    사실 많은 분들이 궁금해하시는 게 검사 과정인데, 저희는 정말 섬세하게 케어해드려요.
    """
    
    try:
        print("🔍 BGN 인터뷰 분석기 테스트 시작...")
        
        # 분석기 초기화
        analyzer = BGNInterviewAnalyzer()
        
        # 인터뷰 분석 실행
        print("📋 인터뷰 분석 중...")
        result = analyzer.analyze_interview(sample_interview)
        
        # 결과 출력
        print("\n✅ 분석 완료!")
        print("\n=== 요약 ===")
        print(analyzer._generate_analysis_summary(result))
        
        print("\n=== 콘텐츠 브리프 ===")
        print(analyzer._generate_content_brief(result))
        
        # 신뢰도 확인
        confidence = result.analysis_metadata['confidence_score']
        print(f"\n📊 분석 신뢰도: {confidence:.2f}")
        
        if confidence >= 0.7:
            print("🎉 높은 신뢰도의 분석 결과입니다!")
        elif confidence >= 0.5:
            print("👍 적당한 신뢰도의 분석 결과입니다.")
        else:
            print("⚠️ 추가 정보가 필요한 분석 결과입니다.")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        print("💡 .env 파일에 OPENAI_API_KEY가 설정되어 있는지 확인하세요.")