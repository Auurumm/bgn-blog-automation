#!/usr/bin/env python3
"""
src/generators/content_generator.py

Import 문제를 해결한 버전
"""

import openai
import re
import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass, asdict
import os
import sys
import random

# 상대 경로 import로 변경
try:
    from ...config.settings import Settings
except ImportError:
    # 절대 경로로 fallback
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from config.settings import Settings

try:
    from ..analyzers.interview_analyzer import (
        InterviewAnalysisResult, EmployeeProfile, PersonalityTraits,
        ProfessionalKnowledge, CustomerInsights, HospitalStrengths
    )
except ImportError:
    # 절대 경로로 fallback
    from src.analyzers.interview_analyzer import (
        InterviewAnalysisResult, EmployeeProfile, PersonalityTraits,
        ProfessionalKnowledge, CustomerInsights, HospitalStrengths
    )

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 나머지 코드는 동일...
@dataclass
class ContentRequest:
    """콘텐츠 생성 요청 데이터"""
    topic: str
    primary_keyword: str
    secondary_keywords: List[str] = None
    target_audience: str = ""
    content_type: str = "A"  # A: 증상/준비형, B: 검사형
    tone_context: str = "상담_안내"  # 상담_안내, 치료_맥락
    min_length: int = 800
    max_length: int = 2500
    include_faq: bool = True
    include_images: bool = True
    
    def __post_init__(self):
        if self.secondary_keywords is None:
            self.secondary_keywords = []

@dataclass
class GeneratedContent:
    """생성된 콘텐츠 데이터"""
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
    generation_metadata: Dict[str, Any]

# 간단한 테스트 함수 추가
def test_imports():
    """Import가 제대로 되는지 테스트"""
    try:
        print("✅ Settings import 성공")
        print(f"병원명: {Settings.HOSPITAL_NAME}")
        return True
    except Exception as e:
        print(f"❌ Import 실패: {str(e)}")
        return False

if __name__ == "__main__":
    print("🔧 Content Generator Import 테스트...")
    test_imports()