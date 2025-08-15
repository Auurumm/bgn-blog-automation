#!/usr/bin/env python3
"""
src/integrations/google_sheets_client.py

📋 역할: 구글 시트 자동 관리 및 콘텐츠 데이터 동기화
- Google Sheets API를 통한 자동 데이터 읽기/쓰기
- 인터뷰 분석 결과를 시트에 자동 입력
- 생성된 콘텐츠 정보 시트 업데이트
- 발행 상태 및 성과 추적 관리
- 콘텐츠 캘린더 자동 생성 및 관리
- 백업 및 버전 관리 기능
- 팀 협업을 위한 공유 시트 관리
- 데이터 검증 및 무결성 확인
"""

import os
import sys
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, timedelta
import logging
import json
from dataclasses import dataclass, asdict
import re

# Google Sheets API
try:
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    import gspread
    from gspread import Spreadsheet, Worksheet
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False
    print("⚠️ Google Sheets 라이브러리 설치 필요: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib gspread")

# 프로젝트 내부 모듈
try:
    from ...config.settings import Settings
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from config.settings import Settings

try:
    from ..analyzers.interview_analyzer import InterviewAnalysisResult
    from ..generators.content_generator import GeneratedContent
    from .wordpress_client import PostPublishResult
except ImportError:
    from src.analyzers.interview_analyzer import InterviewAnalysisResult
    from src.generators.content_generator import GeneratedContent
    from src.integrations.wordpress_client import PostPublishResult

# 로깅 설정
logging.basicConfig(level=getattr(logging, Settings.LOG_LEVEL))
logger = logging.getLogger(__name__)

@dataclass
class SheetsConfig:
    """구글 시트 연결 설정"""
    spreadsheet_id: str
    credentials_file: str
    scopes: List[str] = None
    service_account: bool = True
    
    def __post_init__(self):
        if self.scopes is None:
            self.scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive.file'
            ]

@dataclass 
class SheetData:
    """시트 데이터 행"""
    series: str = ""
    title: str = ""
    primary_keyword: str = ""
    secondary_keywords: str = ""
    tone_context: str = ""
    slug: str = ""
    meta_description: str = ""
    tags: str = ""
    image_prompt_1: str = ""
    image_prompt_2: str = ""
    image_prompt_3: str = ""
    alt_text_1: str = ""
    alt_text_2: str = ""
    alt_text_3: str = ""
    featured_image_filename: str = ""
    image_filenames: str = ""
    internal_links_titles: str = ""
    status: str = "draft"
    medical_ad_compliance_check: str = ""
    content_structure: str = ""
    faq_section: str = ""
    publish_schedule: str = ""
    target_audience: str = ""
    cta_button: str = ""
    related_procedures: str = ""
    # 워드프레스 발행 정보
    wp_post_id: str = ""
    wp_post_url: str = ""
    wp_edit_url: str = ""
    # 메타 정보
    created_date: str = ""
    updated_date: str = ""
    employee_name: str = ""
    seo_score: str = ""
    medical_compliance_score: str = ""

class BGNSheetsClient:
    """BGN 구글 시트 클라이언트"""
    
    def __init__(self, config: SheetsConfig = None):
        """
        구글 시트 클라이언트 초기화
        
        Args:
            config: 구글 시트 설정 (None인 경우 Settings에서 가져옴)
        """
        if not GOOGLE_SHEETS_AVAILABLE:
            raise ImportError("Google Sheets 라이브러리가 설치되지 않았습니다.")
        
        if config is None:
            config = SheetsConfig(
                spreadsheet_id=Settings.GOOGLE_SHEETS_ID,
                credentials_file=Settings.GOOGLE_CREDENTIALS_FILE
            )
        
        self.config = config
        self.gc = None
        self.spreadsheet = None
        self.worksheets = {}
        
        # 시트 헤더 정의
        self._setup_sheet_headers()
        
        # 연결 초기화
        self._initialize_connection()
        
        logger.info(f"BGN 구글 시트 클라이언트 초기화 완료: {config.spreadsheet_id}")
    
    def _setup_sheet_headers(self):
        """시트 헤더 정의"""
        self.main_headers = [
            "series", "title", "primary_keyword", "secondary_keywords", 
            "tone_context", "slug", "meta_description", "tags",
            "image_prompt_1", "image_prompt_2", "image_prompt_3",
            "alt_text_1", "alt_text_2", "alt_text_3",
            "featured_image_filename", "image_filenames", "internal_links_titles",
            "status", "medical_ad_compliance_check", "content_structure",
            "faq_section", "publish_schedule", "target_audience", 
            "cta_button", "related_procedures", "wp_post_id", "wp_post_url",
            "wp_edit_url", "created_date", "updated_date", "employee_name",
            "seo_score", "medical_compliance_score"
        ]
        
        self.header_descriptions = [
            "시리즈 구분 (증상/준비형, 검사형)",
            "블로그 포스트 제목",
            "주요 키워드",
            "보조 키워드 (쉼표 구분)",
            "톤앤매너 맥락",
            "URL 슬러그",
            "메타 설명 (155자 이내)",
            "태그 (쉼표 구분)",
            "이미지 1 프롬프트",
            "이미지 2 프롬프트", 
            "이미지 3 프롬프트",
            "이미지 1 ALT 텍스트",
            "이미지 2 ALT 텍스트",
            "이미지 3 ALT 텍스트",
            "대표 이미지 파일명",
            "모든 이미지 파일명",
            "내부 링크 제목들",
            "발행 상태",
            "의료광고법 준수 체크",
            "콘텐츠 구조 (H2, H3)",
            "FAQ 섹션 (Q: A: 형식)",
            "발행 예정일 (YYYY-MM-DD)",
            "타겟 독자층",
            "CTA 버튼 텍스트",
            "관련 시술명",
            "워드프레스 포스트 ID",
            "워드프레스 포스트 URL",
            "워드프레스 편집 URL",
            "생성일",
            "수정일",
            "담당 직원명",
            "SEO 점수",
            "의료광고법 준수 점수"
        ]
    
    def _initialize_connection(self):
        """구글 시트 연결 초기화"""
        try:
            if self.config.service_account:
                # 서비스 계정 인증
                credentials = ServiceAccountCredentials.from_service_account_file(
                    self.config.credentials_file,
                    scopes=self.config.scopes
                )
            else:
                # OAuth 2.0 인증 (사용자 계정)
                credentials = self._get_oauth_credentials()
            
            self.gc = gspread.authorize(credentials)
            self.spreadsheet = self.gc.open_by_key(self.config.spreadsheet_id)
            
            # 워크시트 정보 캐시
            self._cache_worksheets()
            
            logger.info(f"구글 시트 연결 성공: {self.spreadsheet.title}")
            
        except Exception as e:
            logger.error(f"구글 시트 연결 실패: {str(e)}")
            raise ConnectionError(f"구글 시트 연결 실패: {str(e)}")
    
    def _get_oauth_credentials(self):
        """OAuth 2.0 인증 처리"""
        creds = None
        token_file = 'token.json'
        
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, self.config.scopes)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.config.credentials_file, self.config.scopes)
                creds = flow.run_local_server(port=0)
            
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
        
        return creds
    
    def _cache_worksheets(self):
        """워크시트 정보 캐시"""
        for worksheet in self.spreadsheet.worksheets():
            self.worksheets[worksheet.title] = worksheet
    
    def setup_main_worksheet(self, worksheet_name: str = "콘텐츠 관리") -> bool:
        """메인 워크시트 설정 (헤더 및 기본 구조)"""
        try:
            # 워크시트 생성 또는 가져오기
            try:
                worksheet = self.spreadsheet.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                worksheet = self.spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=1000,
                    cols=len(self.main_headers)
                )
            
            # 헤더 설정
            worksheet.update('A1', [self.main_headers])
            worksheet.update('A2', [self.header_descriptions])
            
            # 헤더 스타일링
            worksheet.format('A1:AG1', {
                'backgroundColor': {'red': 0.2, 'green': 0.53, 'blue': 0.67},
                'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True}
            })
            
            # 설명 행 스타일링
            worksheet.format('A2:AG2', {
                'backgroundColor': {'red': 0.95, 'green': 0.95, 'blue': 0.95},
                'textFormat': {'italic': True, 'fontSize': 9}
            })
            
            # 열 너비 조정
            self._adjust_column_widths(worksheet)
            
            # 캐시 업데이트
            self.worksheets[worksheet_name] = worksheet
            
            logger.info(f"메인 워크시트 설정 완료: {worksheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"워크시트 설정 실패: {str(e)}")
            return False
    
    def _adjust_column_widths(self, worksheet: Worksheet):
        """열 너비 자동 조정"""
        column_widths = {
            'A': 120,  # series
            'B': 300,  # title
            'C': 150,  # primary_keyword
            'D': 200,  # secondary_keywords
            'E': 150,  # tone_context
            'F': 200,  # slug
            'G': 400,  # meta_description
            'H': 200,  # tags
            'I': 300,  # image_prompt_1
            'J': 300,  # image_prompt_2
            'K': 300,  # image_prompt_3
            'L': 200,  # alt_text_1
            'M': 200,  # alt_text_2
            'N': 200,  # alt_text_3
            'O': 200,  # featured_image_filename
            'P': 300,  # image_filenames
            'Q': 300,  # internal_links_titles
            'R': 100,  # status
            'S': 200,  # medical_ad_compliance_check
            'T': 400,  # content_structure
            'U': 500,  # faq_section
            'V': 120,  # publish_schedule
            'W': 150,  # target_audience
            'X': 200,  # cta_button
            'Y': 200,  # related_procedures
            'Z': 100,  # wp_post_id
            'AA': 300, # wp_post_url
            'AB': 300, # wp_edit_url
            'AC': 120, # created_date
            'AD': 120, # updated_date
            'AE': 100, # employee_name
            'AF': 80,  # seo_score
            'AG': 80   # medical_compliance_score
        }
        
        for col, width in column_widths.items():
            try:
                worksheet.update_dimension_properties(
                    col, 'COLUMNS', 'pixelSize', width
                )
            except:
                pass  # 일부 API 제한으로 실패할 수 있음
    
    def add_content_row(self, 
                       analysis_result: InterviewAnalysisResult,
                       generated_content: GeneratedContent,
                       wordpress_result: PostPublishResult = None,
                       worksheet_name: str = "콘텐츠 관리") -> bool:
        """콘텐츠 데이터를 시트에 추가"""
        
        try:
            worksheet = self.worksheets.get(worksheet_name)
            if not worksheet:
                self.setup_main_worksheet(worksheet_name)
                worksheet = self.worksheets[worksheet_name]
            
            # 시트 데이터 객체 생성
            sheet_data = self._create_sheet_data(
                analysis_result, generated_content, wordpress_result
            )
            
            # 다음 빈 행 찾기
            next_row = len(worksheet.get_all_values()) + 1
            
            # 데이터 변환
            row_data = self._convert_to_row_data(sheet_data)
            
            # 행 추가
            worksheet.update(f'A{next_row}', [row_data])
            
            # 상태에 따른 행 색상 설정
            self._apply_status_formatting(worksheet, next_row, sheet_data.status)
            
            logger.info(f"시트에 콘텐츠 추가 완료: {generated_content.title}")
            return True
            
        except Exception as e:
            logger.error(f"시트 데이터 추가 실패: {str(e)}")
            return False
    
    def _create_sheet_data(self, 
                          analysis_result: InterviewAnalysisResult,
                          generated_content: GeneratedContent,
                          wordpress_result: PostPublishResult = None) -> SheetData:
        """시트 데이터 객체 생성"""
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 이미지 프롬프트 분리
        image_prompts = generated_content.image_prompts + ["", "", ""]  # 최소 3개 보장
        
        # FAQ 변환
        faq_text = " || ".join([
            f"Q: {faq['question']} A: {faq['answer']}" 
            for faq in generated_content.faq_list
        ])
        
        sheet_data = SheetData(
            series=self._determine_series_type(generated_content),
            title=generated_content.title,
            primary_keyword=self._extract_primary_keyword(generated_content),
            secondary_keywords=", ".join(generated_content.tags[1:6]),  # 보조 키워드
            tone_context=self._determine_tone_context(analysis_result),
            slug=generated_content.slug,
            meta_description=generated_content.meta_description,
            tags=", ".join(generated_content.tags),
            image_prompt_1=image_prompts[0],
            image_prompt_2=image_prompts[1],
            image_prompt_3=image_prompts[2],
            alt_text_1=f"{generated_content.title} 관련 이미지 1",
            alt_text_2=f"{generated_content.title} 관련 이미지 2", 
            alt_text_3=f"{generated_content.title} 관련 이미지 3",
            featured_image_filename=f"{generated_content.slug}_featured.jpg",
            image_filenames=f"{generated_content.slug}_1.jpg;{generated_content.slug}_2.jpg;{generated_content.slug}_3.jpg",
            internal_links_titles="관련 콘텐츠 링크들",
            status="draft",
            medical_ad_compliance_check=f"의료광고법 준수 점수: {generated_content.medical_compliance_score:.2f}",
            content_structure=self._extract_content_structure(generated_content),
            faq_section=faq_text,
            publish_schedule=datetime.now().strftime("%Y-%m-%d"),
            target_audience=self._determine_target_audience(analysis_result, generated_content),
            cta_button=generated_content.cta_button_text,
            related_procedures=", ".join(analysis_result.knowledge.procedures[:5]),
            created_date=current_time,
            updated_date=current_time,
            employee_name=analysis_result.employee.name,
            seo_score=f"{generated_content.seo_score:.2f}",
            medical_compliance_score=f"{generated_content.medical_compliance_score:.2f}"
        )
        
        # 워드프레스 결과 추가
        if wordpress_result and wordpress_result.success:
            sheet_data.wp_post_id = str(wordpress_result.post_id)
            sheet_data.wp_post_url = wordpress_result.post_url
            sheet_data.wp_edit_url = wordpress_result.edit_url
            sheet_data.status = wordpress_result.status
        
        return sheet_data
    
    def _determine_series_type(self, content: GeneratedContent) -> str:
        """시리즈 타입 결정"""
        if "검사" in content.title or "과정" in content.title:
            return "검사형 (B)"
        elif "준비" in content.title or "가이드" in content.title:
            return "증상/준비형 (A)"
        else:
            return "일반형"
    
    def _extract_primary_keyword(self, content: GeneratedContent) -> str:
        """주요 키워드 추출"""
        if content.tags:
            return content.tags[0]
        
        # 제목에서 키워드 추출
        medical_keywords = ["스마일라식", "라식", "라섹", "백내장", "녹내장", "시력교정"]
        for keyword in medical_keywords:
            if keyword in content.title:
                return keyword
        
        return "안과진료"
    
    def _determine_tone_context(self, analysis: InterviewAnalysisResult) -> str:
        """톤앤매너 맥락 결정"""
        if "상담" in " ".join(analysis.employee.specialty_areas):
            return "상담·안내(고객님 호칭)"
        else:
            return "치료 맥락(환자분 호칭)"
    
    def _extract_content_structure(self, content: GeneratedContent) -> str:
        """콘텐츠 구조 추출"""
        # 마크다운에서 헤딩 구조 추출
        lines = content.content_markdown.split('\n')
        structure_parts = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('## '):
                structure_parts.append(f"H2: {line[3:].strip()}")
            elif line.startswith('### '):
                structure_parts.append(f"H3: {line[4:].strip()}")
        
        return " > ".join(structure_parts[:10])  # 최대 10개
    
    def _determine_target_audience(self, 
                                  analysis: InterviewAnalysisResult, 
                                  content: GeneratedContent) -> str:
        """타겟 독자 결정"""
        audience_hints = []
        
        # 직원 전문분야에서 추출
        for specialty in analysis.employee.specialty_areas:
            if "대학" in specialty:
                audience_hints.append("대학생")
            elif "출장" in specialty:
                audience_hints.append("직장인")
        
        # 콘텐츠에서 추출
        if "대학생" in content.title:
            audience_hints.append("대학생")
        elif "직장인" in content.title:
            audience_hints.append("직장인")
        elif "중장년" in content.title or "어르신" in content.title:
            audience_hints.append("중장년층")
        
        if audience_hints:
            return ", ".join(list(set(audience_hints)))
        else:
            return "일반 고객"
    
    def _convert_to_row_data(self, sheet_data: SheetData) -> List[str]:
        """SheetData를 행 데이터로 변환"""
        return [
            sheet_data.series,
            sheet_data.title,
            sheet_data.primary_keyword,
            sheet_data.secondary_keywords,
            sheet_data.tone_context,
            sheet_data.slug,
            sheet_data.meta_description,
            sheet_data.tags,
            sheet_data.image_prompt_1,
            sheet_data.image_prompt_2,
            sheet_data.image_prompt_3,
            sheet_data.alt_text_1,
            sheet_data.alt_text_2,
            sheet_data.alt_text_3,
            sheet_data.featured_image_filename,
            sheet_data.image_filenames,
            sheet_data.internal_links_titles,
            sheet_data.status,
            sheet_data.medical_ad_compliance_check,
            sheet_data.content_structure,
            sheet_data.faq_section,
            sheet_data.publish_schedule,
            sheet_data.target_audience,
            sheet_data.cta_button,
            sheet_data.related_procedures,
            sheet_data.wp_post_id,
            sheet_data.wp_post_url,
            sheet_data.wp_edit_url,
            sheet_data.created_date,
            sheet_data.updated_date,
            sheet_data.employee_name,
            sheet_data.seo_score,
            sheet_data.medical_compliance_score
        ]
    
    def _apply_status_formatting(self, worksheet: Worksheet, row: int, status: str):
        """상태에 따른 행 포맷팅"""
        
        status_colors = {
            "draft": {"red": 1, "green": 0.95, "blue": 0.8},      # 연한 노랑
            "publish": {"red": 0.85, "green": 1, "blue": 0.85},   # 연한 초록
            "private": {"red": 0.95, "green": 0.95, "blue": 0.95}, # 연한 회색
            "failed": {"red": 1, "green": 0.85, "blue": 0.85}     # 연한 빨강
        }
        
        color = status_colors.get(status, {"red": 1, "green": 1, "blue": 1})
        
        try:
            worksheet.format(f'A{row}:AG{row}', {
                'backgroundColor': color
            })
        except Exception as e:
            logger.warning(f"행 포맷팅 실패: {str(e)}")
    
    def update_wordpress_status(self, 
                               title: str,
                               wordpress_result: PostPublishResult,
                               worksheet_name: str = "콘텐츠 관리") -> bool:
        """워드프레스 발행 결과로 시트 업데이트"""
        
        try:
            worksheet = self.worksheets.get(worksheet_name)
            if not worksheet:
                return False
            
            # 제목으로 행 찾기
            all_values = worksheet.get_all_values()
            target_row = None
            
            for i, row in enumerate(all_values[2:], start=3):  # 헤더 2행 제외
                if len(row) > 1 and row[1] == title:  # B열이 title
                    target_row = i
                    break
            
            if not target_row:
                logger.warning(f"시트에서 제목을 찾을 수 없음: {title}")
                return False
            
            # 워드프레스 정보 업데이트
            updates = [
                (f'Z{target_row}', str(wordpress_result.post_id)),      # wp_post_id
                (f'AA{target_row}', wordpress_result.post_url),         # wp_post_url
                (f'AB{target_row}', wordpress_result.edit_url),         # wp_edit_url
                (f'R{target_row}', wordpress_result.status),            # status
                (f'AD{target_row}', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))  # updated_date
            ]
            
            for cell, value in updates:
                worksheet.update(cell, value)
            
            # 상태 포맷팅 업데이트
            self._apply_status_formatting(worksheet, target_row, wordpress_result.status)
            
            logger.info(f"워드프레스 상태 업데이트 완료: {title}")
            return True
            
        except Exception as e:
            logger.error(f"워드프레스 상태 업데이트 실패: {str(e)}")
            return False
    
    def get_content_list(self, 
                        status_filter: str = None,
                        employee_filter: str = None,
                        worksheet_name: str = "콘텐츠 관리") -> List[Dict]:
        """시트에서 콘텐츠 목록 조회"""
        
        try:
            worksheet = self.worksheets.get(worksheet_name)
            if not worksheet:
                return []
            
            all_values = worksheet.get_all_values()
            if len(all_values) < 3:  # 헤더 2행 + 데이터 최소 1행
                return []
            
            headers = all_values[0]
            content_list = []
            
            for row in all_values[2:]:  # 헤더 2행 제외
                if len(row) < len(headers):
                    continue  # 불완전한 행 스킵
                
                # 딕셔너리로 변환
                content_dict = dict(zip(headers, row))
                
                # 필터 적용
                if status_filter and content_dict.get('status') != status_filter:
                    continue
                
                if employee_filter and content_dict.get('employee_name') != employee_filter:
                    continue
                
                content_list.append(content_dict)
            
            return content_list
            
        except Exception as e:
            logger.error(f"콘텐츠 목록 조회 실패: {str(e)}")
            return []
    
    def create_content_calendar(self, 
                               worksheet_name: str = "콘텐츠 캘린더") -> bool:
        """콘텐츠 캘린더 시트 생성"""
        
        try:
            # 메인 시트에서 데이터 가져오기
            content_list = self.get_content_list()
            
            if not content_list:
                logger.warning("콘텐츠 데이터가 없어 캘린더를 생성할 수 없습니다.")
                return False
            
            # 캘린더 워크시트 생성 또는 가져오기
            try:
                calendar_ws = self.spreadsheet.worksheet(worksheet_name)
                calendar_ws.clear()  # 기존 데이터 클리어
            except gspread.WorksheetNotFound:
                calendar_ws = self.spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=500,
                    cols=10
                )
            
            # 캘린더 헤더 설정
            calendar_headers = [
                "발행일", "요일", "제목", "시리즈", "담당자", 
                "상태", "워드프레스 URL", "SEO 점수", "조회수", "비고"
            ]
            
            calendar_ws.update('A1', [calendar_headers])
            
            # 헤더 스타일링
            calendar_ws.format('A1:J1', {
                'backgroundColor': {'red': 0.2, 'green': 0.7, 'blue': 0.9},
                'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True}
            })
            
            # 데이터 정렬 (발행일 기준)
            sorted_content = sorted(
                content_list, 
                key=lambda x: x.get('publish_schedule', '2099-12-31')
            )
            
            # 캘린더 데이터 생성
            calendar_data = []
            for content in sorted_content:
                publish_date = content.get('publish_schedule', '')
                if publish_date:
                    try:
                        date_obj = datetime.strptime(publish_date, '%Y-%m-%d')
                        weekday = ['월', '화', '수', '목', '금', '토', '일'][date_obj.weekday()]
                    except:
                        weekday = ''
                else:
                    weekday = ''
                
                calendar_data.append([
                    publish_date,
                    weekday,
                    content.get('title', ''),
                    content.get('series', ''),
                    content.get('employee_name', ''),
                    content.get('status', ''),
                    content.get('wp_post_url', ''),
                    content.get('seo_score', ''),
                    '',  # 조회수 (추후 연동)
                    ''   # 비고
                ])
            
            # 데이터 업데이트
            if calendar_data:
                calendar_ws.update('A2', calendar_data)
                
                # 상태별 색상 적용
                self._apply_calendar_formatting(calendar_ws, calendar_data)
            
            # 캘린더 워크시트 캐시 업데이트
            self.worksheets[worksheet_name] = calendar_ws
            
            logger.info(f"콘텐츠 캘린더 생성 완료: {len(calendar_data)}개 항목")
            return True
            
        except Exception as e:
            logger.error(f"콘텐츠 캘린더 생성 실패: {str(e)}")
            return False
    
    def _apply_calendar_formatting(self, worksheet: Worksheet, calendar_data: List[List]):
        """캘린더 포맷팅 적용"""
        
        try:
            for i, row in enumerate(calendar_data, start=2):
                status = row[5] if len(row) > 5 else ''
                
                if status == 'publish':
                    # 발행됨 - 초록색
                    worksheet.format(f'A{i}:J{i}', {
                        'backgroundColor': {'red': 0.85, 'green': 1, 'blue': 0.85}
                    })
                elif status == 'draft':
                    # 초안 - 노란색
                    worksheet.format(f'A{i}:J{i}', {
                        'backgroundColor': {'red': 1, 'green': 0.95, 'blue': 0.8}
                    })
                elif status == 'failed':
                    # 실패 - 빨간색
                    worksheet.format(f'A{i}:J{i}', {
                        'backgroundColor': {'red': 1, 'green': 0.85, 'blue': 0.85}
                    })
                
                # 주말 표시 (토, 일)
                weekday = row[1] if len(row) > 1 else ''
                if weekday in ['토', '일']:
                    worksheet.format(f'B{i}', {
                        'textFormat': {'foregroundColor': {'red': 1, 'green': 0, 'blue': 0}}
                    })
        
        except Exception as e:
            logger.warning(f"캘린더 포맷팅 실패: {str(e)}")
    
    def create_analytics_dashboard(self, 
                                  worksheet_name: str = "성과 분석") -> bool:
        """성과 분석 대시보드 생성"""
        
        try:
            # 분석 워크시트 생성
            try:
                analytics_ws = self.spreadsheet.worksheet(worksheet_name)
                analytics_ws.clear()
            except gspread.WorksheetNotFound:
                analytics_ws = self.spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=100,
                    cols=10
                )
            
            content_list = self.get_content_list()
            
            # 대시보드 구성
            dashboard_data = [
                ["📊 BGN 블로그 성과 분석 대시보드", "", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", ""],
                ["📈 전체 통계", "", "", "", "", "", "", "", "", ""],
                ["총 콘텐츠 수", len(content_list), "", "", "", "", "", "", "", ""],
                ["발행된 포스트", len([c for c in content_list if c.get('status') == 'publish']), "", "", "", "", "", "", "", ""],
                ["초안 상태", len([c for c in content_list if c.get('status') == 'draft']), "", "", "", "", "", "", "", ""],
                ["평균 SEO 점수", self._calculate_average_seo_score(content_list), "", "", "", "", "", "", "", ""],
                ["의료광고법 준수율", f"{self._calculate_compliance_rate(content_list)}%", "", "", "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", "", ""],
                ["👥 직원별 기여도", "", "", "", "", "", "", "", "", ""],
            ]
            
            # 직원별 통계
            employee_stats = self._calculate_employee_stats(content_list)
            for employee, stats in employee_stats.items():
                dashboard_data.append([
                    employee,
                    f"총 {stats['total']}개",
                    f"발행 {stats['published']}개",
                    f"평균 SEO {stats['avg_seo']:.1f}",
                    "", "", "", "", "", ""
                ])
            
            dashboard_data.extend([
                ["", "", "", "", "", "", "", "", "", ""],
                ["📅 월별 발행 현황", "", "", "", "", "", "", "", "", ""],
            ])
            
            # 월별 통계
            monthly_stats = self._calculate_monthly_stats(content_list)
            for month, count in monthly_stats.items():
                dashboard_data.append([month, f"{count}개 발행", "", "", "", "", "", "", "", ""])
            
            # 데이터 업데이트
            analytics_ws.update('A1', dashboard_data)
            
            # 스타일링
            analytics_ws.format('A1:J1', {
                'backgroundColor': {'red': 0.2, 'green': 0.53, 'blue': 0.67},
                'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True, 'fontSize': 14}
            })
            
            analytics_ws.format('A3:A3', {
                'backgroundColor': {'red': 0.85, 'green': 0.85, 'blue': 0.85},
                'textFormat': {'bold': True}
            })
            
            analytics_ws.format('A10:A10', {
                'backgroundColor': {'red': 0.85, 'green': 0.85, 'blue': 0.85},
                'textFormat': {'bold': True}
            })
            
            # 워크시트 캐시 업데이트
            self.worksheets[worksheet_name] = analytics_ws
            
            logger.info("성과 분석 대시보드 생성 완료")
            return True
            
        except Exception as e:
            logger.error(f"분석 대시보드 생성 실패: {str(e)}")
            return False
    
    def _calculate_average_seo_score(self, content_list: List[Dict]) -> str:
        """평균 SEO 점수 계산"""
        scores = []
        for content in content_list:
            try:
                score = float(content.get('seo_score', '0'))
                scores.append(score)
            except:
                continue
        
        if scores:
            return f"{sum(scores) / len(scores):.2f}"
        return "0.00"
    
    def _calculate_compliance_rate(self, content_list: List[Dict]) -> int:
        """의료광고법 준수율 계산"""
        compliant_count = 0
        total_count = 0
        
        for content in content_list:
            try:
                score = float(content.get('medical_compliance_score', '0'))
                total_count += 1
                if score >= 0.8:  # 80% 이상을 준수로 간주
                    compliant_count += 1
            except:
                continue
        
        if total_count > 0:
            return int((compliant_count / total_count) * 100)
        return 100
    
    def _calculate_employee_stats(self, content_list: List[Dict]) -> Dict[str, Dict]:
        """직원별 통계 계산"""
        employee_stats = {}
        
        for content in content_list:
            employee = content.get('employee_name', '미상')
            if employee not in employee_stats:
                employee_stats[employee] = {
                    'total': 0,
                    'published': 0,
                    'seo_scores': []
                }
            
            employee_stats[employee]['total'] += 1
            
            if content.get('status') == 'publish':
                employee_stats[employee]['published'] += 1
            
            try:
                seo_score = float(content.get('seo_score', '0'))
                employee_stats[employee]['seo_scores'].append(seo_score)
            except:
                pass
        
        # 평균 SEO 점수 계산
        for employee, stats in employee_stats.items():
            if stats['seo_scores']:
                stats['avg_seo'] = sum(stats['seo_scores']) / len(stats['seo_scores'])
            else:
                stats['avg_seo'] = 0.0
        
        return employee_stats
    
    def _calculate_monthly_stats(self, content_list: List[Dict]) -> Dict[str, int]:
        """월별 발행 통계 계산"""
        monthly_stats = {}
        
        for content in content_list:
            if content.get('status') != 'publish':
                continue
            
            publish_date = content.get('publish_schedule', '')
            if publish_date:
                try:
                    date_obj = datetime.strptime(publish_date, '%Y-%m-%d')
                    month_key = date_obj.strftime('%Y년 %m월')
                    monthly_stats[month_key] = monthly_stats.get(month_key, 0) + 1
                except:
                    continue
        
        return dict(sorted(monthly_stats.items()))
    
    def backup_spreadsheet(self, backup_name: str = None) -> str:
        """스프레드시트 백업"""
        
        try:
            if backup_name is None:
                backup_name = f"BGN_블로그_백업_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 스프레드시트 복사
            backup_sheet = self.gc.copy(
                self.config.spreadsheet_id,
                title=backup_name,
                copy_permissions=True
            )
            
            backup_url = f"https://docs.google.com/spreadsheets/d/{backup_sheet.id}"
            
            logger.info(f"스프레드시트 백업 완료: {backup_name}")
            return backup_url
            
        except Exception as e:
            logger.error(f"스프레드시트 백업 실패: {str(e)}")
            return ""
    
    def export_to_json(self, 
                      worksheet_name: str = "콘텐츠 관리",
                      output_file: str = None) -> str:
        """시트 데이터를 JSON으로 내보내기"""
        
        try:
            content_list = self.get_content_list(worksheet_name=worksheet_name)
            
            if output_file is None:
                output_file = f"data/exports/bgn_content_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            export_data = {
                "export_date": datetime.now().isoformat(),
                "total_content": len(content_list),
                "content_list": content_list
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"JSON 내보내기 완료: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"JSON 내보내기 실패: {str(e)}")
            return ""
    
    def get_client_stats(self) -> Dict[str, Any]:
        """클라이언트 통계 정보"""
        
        content_list = self.get_content_list()
        
        return {
            "spreadsheet_id": self.config.spreadsheet_id,
            "spreadsheet_title": self.spreadsheet.title if self.spreadsheet else "Unknown",
            "worksheets_count": len(self.worksheets),
            "total_content": len(content_list),
            "published_content": len([c for c in content_list if c.get('status') == 'publish']),
            "draft_content": len([c for c in content_list if c.get('status') == 'draft']),
            "connection_status": "Connected" if self.gc else "Disconnected"
        }

# 유틸리티 함수들
def create_bgn_sheets_client(spreadsheet_id: str = None,
                            credentials_file: str = None) -> BGNSheetsClient:
    """BGN 구글 시트 클라이언트 생성 (편의 함수)"""
    config = SheetsConfig(
        spreadsheet_id=spreadsheet_id or Settings.GOOGLE_SHEETS_ID,
        credentials_file=credentials_file or Settings.GOOGLE_CREDENTIALS_FILE
    )
    return BGNSheetsClient(config)

def quick_add_content_to_sheet(analysis_result: InterviewAnalysisResult,
                              generated_content: GeneratedContent,
                              wordpress_result: PostPublishResult = None) -> bool:
    """빠른 시트 추가 (편의 함수)"""
    try:
        client = create_bgn_sheets_client()
        return client.add_content_row(analysis_result, generated_content, wordpress_result)
    except Exception as e:
        logger.error(f"빠른 시트 추가 실패: {str(e)}")
        return False

# 사용 예시 및 테스트
if __name__ == "__main__":
    try:
        print("📊 BGN 구글 시트 클라이언트 테스트 시작...")
        
        # 라이브러리 확인
        if not GOOGLE_SHEETS_AVAILABLE:
            print("❌ Google Sheets 라이브러리가 설치되지 않았습니다.")
            print("💡 설치 명령어: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib gspread")
            exit(1)
        
        # 설정 확인
        if not Settings.GOOGLE_SHEETS_ID:
            print("❌ 구글 시트 ID가 설정되지 않았습니다.")
            print("💡 .env 파일에 GOOGLE_SHEETS_ID를 설정하세요.")
            exit(1)
        
        if not os.path.exists(Settings.GOOGLE_CREDENTIALS_FILE):
            print("❌ 구글 인증 파일이 없습니다.")
            print("💡 Google Cloud Console에서 서비스 계정 키를 생성하고 credentials.json으로 저장하세요.")
            exit(1)
        
        print("⚙️ 구글 시트 클라이언트 초기화 중...")
        client = create_bgn_sheets_client()
        
        print("✅ 구글 시트 연결 성공!")
        
        # 통계 확인
        stats = client.get_client_stats()
        print(f"📊 시트 정보:")
        print(f"  - 제목: {stats['spreadsheet_title']}")
        print(f"  - 워크시트 수: {stats['worksheets_count']}")
        print(f"  - 총 콘텐츠: {stats['total_content']}")
        print(f"  - 발행된 콘텐츠: {stats['published_content']}")
        print(f"  - 초안 콘텐츠: {stats['draft_content']}")
        
        # 메인 워크시트 설정 테스트
        print("\n🔧 메인 워크시트 설정 중...")
        setup_success = client.setup_main_worksheet()
        
        if setup_success:
            print("✅ 메인 워크시트 설정 완료!")
        else:
            print("❌ 메인 워크시트 설정 실패")
        
        # 콘텐츠 캘린더 생성 테스트
        print("\n📅 콘텐츠 캘린더 생성 중...")
        calendar_success = client.create_content_calendar()
        
        if calendar_success:
            print("✅ 콘텐츠 캘린더 생성 완료!")
        else:
            print("⚠️ 콘텐츠 캘린더 생성 실패 (데이터 부족 가능)")
        
        # 분석 대시보드 생성 테스트
        print("\n📈 분석 대시보드 생성 중...")
        dashboard_success = client.create_analytics_dashboard()
        
        if dashboard_success:
            print("✅ 분석 대시보드 생성 완료!")
        else:
            print("⚠️ 분석 대시보드 생성 실패")
        
        print(f"\n🎉 모든 테스트 완료!")
        print(f"📋 구글 시트 URL: https://docs.google.com/spreadsheets/d/{Settings.GOOGLE_SHEETS_ID}")
        
        print("\n📋 사용 방법:")
        print("```python")
        print("from src.integrations.google_sheets_client import create_bgn_sheets_client")
        print("")
        print("# 클라이언트 생성")
        print("client = create_bgn_sheets_client()")
        print("")
        print("# 콘텐츠 추가")
        print("client.add_content_row(analysis_result, generated_content, wordpress_result)")
        print("")
        print("# 워드프레스 상태 업데이트")
        print("client.update_wordpress_status(title, wordpress_result)")
        print("```")
        
    except ConnectionError as e:
        print(f"❌ 연결 실패: {str(e)}")
        print("💡 구글 시트 ID와 인증 파일을 확인하세요.")
        print("💡 구글 시트 공유 설정을 확인하세요.")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        print("💡 설정을 확인하고 다시 시도하세요.")