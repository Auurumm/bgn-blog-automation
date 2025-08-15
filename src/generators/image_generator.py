#!/usr/bin/env python3
"""
src/generators/image_generator.py

📋 역할: DALL-E를 활용한 의료용 이미지 자동 생성
- OpenAI DALL-E 3 API를 통한 고품질 이미지 생성
- 의료광고법 준수하는 프롬프트 최적화
- BGN 병원 브랜딩 가이드라인 반영
- 다양한 의료 스타일 이미지 생성 (깔끔한 의료용, 인포그래픽, 장비 중심)
- 이미지 품질 관리 및 최적화
- 생성 실패 시 재시도 및 에러 처리
"""

import openai
import requests
import base64
from PIL import Image, ImageEnhance, ImageFilter
import io
import os
from typing import Optional, Tuple, List, Dict
import time
import logging
from datetime import datetime

# 프로젝트 내부 모듈
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config.settings import Settings

# 로깅 설정
logging.basicConfig(level=getattr(logging, Settings.LOG_LEVEL))
logger = logging.getLogger(__name__)

class BGNImageGenerator:
    """BGN 병원 전용 DALL-E 이미지 생성기"""
    
    def __init__(self, api_key: str = None):
        """
        이미지 생성기 초기화
        
        Args:
            api_key: OpenAI API 키 (None인 경우 settings에서 가져옴)
        """
        self.api_key = api_key or Settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API 키가 설정되지 않았습니다.")
        
        self.client = openai.OpenAI(api_key=self.api_key)
        self.generation_count = 0
        self.failed_generations = []
        
        logger.info("BGN 이미지 생성기가 초기화되었습니다.")
    
    def generate_medical_image(self, 
                             prompt: str, 
                             style: str = "medical_clean",
                             content_type: str = "general",
                             retry_attempts: int = 3) -> Tuple[Optional[Image.Image], Optional[str], Dict]:
        """
        의료용 이미지 생성
        
        Args:
            prompt: 기본 이미지 설명
            style: 이미지 스타일 (medical_clean, infographic, equipment)
            content_type: 콘텐츠 타입 (procedure, examination, consultation, equipment)
            retry_attempts: 재시도 횟수
            
        Returns:
            Tuple[PIL.Image, 이미지 URL, 생성 메타데이터]
        """
        logger.info(f"이미지 생성 시작: {prompt[:50]}...")
        
        # 의료용 프롬프트 최적화
        enhanced_prompt = self._enhance_medical_prompt(prompt, style, content_type)
        
        # 의료광고법 준수 검증
        if not self._validate_medical_compliance(enhanced_prompt):
            logger.warning("의료광고법 위반 가능성이 있는 프롬프트입니다.")
            enhanced_prompt = self._sanitize_prompt(enhanced_prompt)
        
        # 생성 메타데이터
        metadata = {
            "original_prompt": prompt,
            "enhanced_prompt": enhanced_prompt,
            "style": style,
            "content_type": content_type,
            "generation_time": datetime.now().isoformat(),
            "attempts": 0,
            "success": False
        }
        
        # 재시도 로직
        for attempt in range(retry_attempts):
            try:
                metadata["attempts"] = attempt + 1
                logger.info(f"이미지 생성 시도 {attempt + 1}/{retry_attempts}")
                
                # DALL-E 3 API 호출
                response = self.client.images.generate(
                    model=Settings.DALLE_MODEL,
                    prompt=enhanced_prompt,
                    size=Settings.DALLE_SIZE,
                    quality=Settings.DALLE_QUALITY,
                    n=1,
                )
                
                image_url = response.data[0].url
                
                # 이미지 다운로드 및 처리
                image = self._download_and_process_image(image_url)
                
                if image:
                    self.generation_count += 1
                    metadata["success"] = True
                    metadata["image_url"] = image_url
                    
                    logger.info(f"이미지 생성 성공! (시도 {attempt + 1}회)")
                    return image, image_url, metadata
                
            except openai.APIError as e:
                logger.error(f"OpenAI API 오류 (시도 {attempt + 1}): {str(e)}")
                if "rate limit" in str(e).lower():
                    time.sleep(60)  # Rate limit 시 1분 대기
                elif attempt < retry_attempts - 1:
                    time.sleep(5)  # 일반 오류 시 5초 대기
                    
            except Exception as e:
                logger.error(f"이미지 생성 오류 (시도 {attempt + 1}): {str(e)}")
                if attempt < retry_attempts - 1:
                    time.sleep(3)
        
        # 모든 시도 실패
        logger.error(f"이미지 생성 완전 실패: {prompt}")
        self.failed_generations.append({
            "prompt": prompt,
            "error": "최대 재시도 횟수 초과",
            "timestamp": datetime.now()
        })
        
        return None, None, metadata
    
    def _enhance_medical_prompt(self, 
                               base_prompt: str, 
                               style: str, 
                               content_type: str) -> str:
        """
        의료용 프롬프트 강화 및 최적화
        
        Args:
            base_prompt: 기본 프롬프트
            style: 이미지 스타일
            content_type: 콘텐츠 타입
            
        Returns:
            최적화된 프롬프트
        """
        # 스타일별 접미사
        style_suffix = Settings.IMAGE_STYLES.get(style, Settings.IMAGE_STYLES["medical_clean"])["prompt_suffix"]
        
        # 콘텐츠 타입별 특화 요소
        content_elements = {
            "procedure": "surgical procedure illustration, step by step process, medical accuracy",
            "examination": "diagnostic equipment, patient examination, clinical setting",
            "consultation": "doctor patient consultation, comfortable medical environment",
            "equipment": "advanced medical devices, precision instruments, technical accuracy",
            "general": "healthcare information, medical education, patient guidance"
        }
        
        content_element = content_elements.get(content_type, content_elements["general"])
        
        # 의료광고법 준수 요소
        compliance_elements = [
            "educational purpose only",
            "general information illustration", 
            "not showing specific medical results",
            "professional medical setting",
            "no patient identification visible"
        ]
        
        # BGN 브랜딩 요소
        brand_elements = Settings.get_brand_prompt_suffix()
        
        # 한국 의료 환경 특화
        korean_medical_elements = [
            "Korean hospital standard",
            "modern Korean medical facility",
            "clean and organized medical environment"
        ]
        
        # 품질 보장 요소
        quality_elements = [
            "high resolution",
            "professional photography quality",
            "clear and detailed",
            "medically accurate",
            "appropriate lighting"
        ]
        
        # 최종 프롬프트 조합
        enhanced_prompt = f"""
        {base_prompt}, 
        {content_element}, 
        {style_suffix}, 
        {', '.join(compliance_elements[:2])}, 
        {', '.join(korean_medical_elements[:2])}, 
        {brand_elements}, 
        {', '.join(quality_elements[:3])}
        """.strip().replace('\n', ' ').replace('  ', ' ')
        
        # 길이 제한 (DALL-E 3는 4000자 제한)
        if len(enhanced_prompt) > 3000:
            enhanced_prompt = enhanced_prompt[:3000] + "..."
        
        logger.debug(f"강화된 프롬프트: {enhanced_prompt[:100]}...")
        return enhanced_prompt
    
    def _validate_medical_compliance(self, prompt: str) -> bool:
        """
        의료광고법 준수 여부 검증
        
        Args:
            prompt: 검증할 프롬프트
            
        Returns:
            True if 준수, False if 위반 가능성
        """
        prompt_lower = prompt.lower()
        
        # 금지 키워드 검사
        for keyword in Settings.PROHIBITED_KEYWORDS:
            if keyword.lower() in prompt_lower:
                logger.warning(f"금지 키워드 감지: {keyword}")
                return False
        
        # 과장된 효과 표현 검사
        risky_phrases = [
            "perfect result", "guaranteed outcome", "best hospital",
            "number one", "100% success", "miraculous"
        ]
        
        for phrase in risky_phrases:
            if phrase.lower() in prompt_lower:
                logger.warning(f"위험한 표현 감지: {phrase}")
                return False
        
        return True
    
    def _sanitize_prompt(self, prompt: str) -> str:
        """
        프롬프트 정화 (위험한 표현 제거/대체)
        
        Args:
            prompt: 원본 프롬프트
            
        Returns:
            정화된 프롬프트
        """
        sanitized = prompt
        
        # 금지 키워드 대체
        for prohibited, alternative in Settings.RECOMMENDED_ALTERNATIVES.items():
            sanitized = sanitized.replace(prohibited, alternative)
        
        # 과장된 표현 제거
        risky_replacements = {
            "perfect": "professional",
            "best": "quality", 
            "number one": "leading",
            "guaranteed": "reliable",
            "miraculous": "effective"
        }
        
        for risky, safe in risky_replacements.items():
            sanitized = sanitized.replace(risky, safe)
        
        logger.info("프롬프트가 의료광고법 준수를 위해 수정되었습니다.")
        return sanitized
    
    def _download_and_process_image(self, image_url: str) -> Optional[Image.Image]:
        """
        이미지 다운로드 및 후처리
        
        Args:
            image_url: 이미지 URL
            
        Returns:
            처리된 PIL Image 객체
        """
        try:
            # 이미지 다운로드
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            # PIL Image로 변환
            image = Image.open(io.BytesIO(response.content))
            
            # 기본 후처리
            image = self._apply_bgn_post_processing(image)
            
            logger.debug("이미지 다운로드 및 처리 완료")
            return image
            
        except Exception as e:
            logger.error(f"이미지 다운로드 실패: {str(e)}")
            return None
    
    def _apply_bgn_post_processing(self, image: Image.Image) -> Image.Image:
        """
        BGN 브랜딩에 맞는 이미지 후처리
        
        Args:
            image: 원본 이미지
            
        Returns:
            후처리된 이미지
        """
        try:
            # RGB 모드로 변환
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # 약간의 선명도 향상
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.1)
            
            # 색상 채도 미세 조정 (의료용 차분한 톤)
            enhancer = ImageEnhance.Color(image)
            image = enhancer.enhance(0.95)
            
            # 밝기 미세 조정
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(1.05)
            
            logger.debug("BGN 브랜딩 후처리 완료")
            return image
            
        except Exception as e:
            logger.warning(f"후처리 실패, 원본 이미지 반환: {str(e)}")
            return image
    
    def generate_blog_images(self, 
                           content_data: Dict, 
                           style: str = "medical_clean") -> List[Tuple[Image.Image, str, str]]:
        """
        블로그 포스트용 이미지 세트 생성
        
        Args:
            content_data: 콘텐츠 데이터 (title, keywords, content_type 등)
            style: 이미지 스타일
            
        Returns:
            List of (Image, URL, ALT_TEXT) tuples
        """
        logger.info(f"블로그 이미지 세트 생성 시작: {content_data.get('title', 'Unknown')}")
        
        # 기본 이미지 프롬프트들
        base_prompts = [
            f"Professional medical consultation about {content_data.get('primary_keyword', 'eye care')} in modern hospital",
            f"Advanced medical equipment for {content_data.get('primary_keyword', 'eye examination')} in clean clinical setting", 
            f"Patient education materials about {content_data.get('primary_keyword', 'vision health')} in comfortable environment"
        ]
        
        # 추가 프롬프트가 있다면 사용
        if 'image_prompts' in content_data:
            base_prompts = content_data['image_prompts'][:Settings.MAX_IMAGES_PER_POST]
        
        generated_images = []
        
        for i, prompt in enumerate(base_prompts):
            logger.info(f"이미지 {i+1}/{len(base_prompts)} 생성 중...")
            
            # 콘텐츠 타입 결정
            content_type = "general"
            if "검사" in content_data.get('title', ''):
                content_type = "examination"
            elif "수술" in content_data.get('title', ''):
                content_type = "procedure"
            elif "상담" in content_data.get('title', ''):
                content_type = "consultation"
            
            # 이미지 생성
            image, url, metadata = self.generate_medical_image(
                prompt=prompt,
                style=style,
                content_type=content_type
            )
            
            if image and url:
                # ALT 텍스트 생성
                alt_text = self._generate_alt_text(content_data, i+1)
                generated_images.append((image, url, alt_text))
                
                logger.info(f"이미지 {i+1} 생성 성공")
            else:
                logger.warning(f"이미지 {i+1} 생성 실패")
        
        logger.info(f"블로그 이미지 세트 생성 완료: {len(generated_images)}개 성공")
        return generated_images
    
    def _generate_alt_text(self, content_data: Dict, image_number: int) -> str:
        """
        SEO 및 접근성을 위한 ALT 텍스트 생성
        
        Args:
            content_data: 콘텐츠 데이터
            image_number: 이미지 번호
            
        Returns:
            최적화된 ALT 텍스트
        """
        hospital_name = Settings.HOSPITAL_NAME
        keyword = content_data.get('primary_keyword', '안과 진료')
        
        alt_templates = [
            f"{hospital_name} {keyword} 전문 상담 이미지",
            f"{keyword} 정밀 검사를 위한 최신 의료 장비",
            f"{hospital_name}의 {keyword} 환자 안내 및 교육 자료"
        ]
        
        if image_number <= len(alt_templates):
            return alt_templates[image_number - 1]
        else:
            return f"{hospital_name} {keyword} 관련 의료 정보 이미지"
    
    def save_image(self, 
                   image: Image.Image, 
                   filename: str, 
                   save_dir: str = "data/generated/images") -> str:
        """
        이미지를 파일로 저장
        
        Args:
            image: PIL Image 객체
            filename: 파일명 (확장자 제외)
            save_dir: 저장 디렉토리
            
        Returns:
            저장된 파일 경로
        """
        os.makedirs(save_dir, exist_ok=True)
        
        # 파일명 정리
        clean_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_')).rstrip()
        file_path = os.path.join(save_dir, f"{clean_filename}.jpg")
        
        # 중복 파일명 처리
        counter = 1
        while os.path.exists(file_path):
            file_path = os.path.join(save_dir, f"{clean_filename}_{counter}.jpg")
            counter += 1
        
        # 이미지 저장
        image.save(file_path, "JPEG", quality=95, optimize=True)
        
        logger.info(f"이미지 저장 완료: {file_path}")
        return file_path
    
    def get_generation_stats(self) -> Dict:
        """
        이미지 생성 통계 반환
        
        Returns:
            생성 통계 딕셔너리
        """
        return {
            "total_generated": self.generation_count,
            "failed_generations": len(self.failed_generations),
            "success_rate": self.generation_count / (self.generation_count + len(self.failed_generations)) if (self.generation_count + len(self.failed_generations)) > 0 else 0,
            "recent_failures": self.failed_generations[-5:] if self.failed_generations else []
        }

# 사용 예시 및 테스트
if __name__ == "__main__":
    # 테스트용 이미지 생성기 초기화
    try:
        generator = BGNImageGenerator()
        
        # 테스트 이미지 생성
        test_prompt = "university students consulting about vision correction surgery"
        
        print("🎨 테스트 이미지 생성 중...")
        image, url, metadata = generator.generate_medical_image(
            prompt=test_prompt,
            style="medical_clean",
            content_type="consultation"
        )
        
        if image:
            print("✅ 이미지 생성 성공!")
            print(f"📊 메타데이터: {metadata}")
            
            # 저장 테스트
            saved_path = generator.save_image(image, "test_consultation")
            print(f"💾 이미지 저장: {saved_path}")
        else:
            print("❌ 이미지 생성 실패")
        
        # 통계 출력
        stats = generator.get_generation_stats()
        print(f"📈 생성 통계: {stats}")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {str(e)}")
        print("💡 .env 파일에 OPENAI_API_KEY가 설정되어 있는지 확인하세요.")