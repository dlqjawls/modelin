"""
Modelin - Supabase 데이터베이스 클라이언트
"""
from supabase import create_client, Client
from config import settings


_supabase_client: Client | None = None


def get_supabase() -> Client:
    """Supabase 클라이언트 싱글턴"""
    global _supabase_client
    if _supabase_client is None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise ValueError(
                "SUPABASE_URL과 SUPABASE_KEY 환경변수를 설정해주세요. "
                ".env.example 파일을 참고하세요."
            )
        _supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _supabase_client


def get_supabase_admin() -> Client:
    """서비스 롤 키를 사용하는 Supabase 클라이언트 (RLS 우회)"""
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise ValueError(
            "SUPABASE_URL과 SUPABASE_SERVICE_KEY 환경변수를 설정해주세요."
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
