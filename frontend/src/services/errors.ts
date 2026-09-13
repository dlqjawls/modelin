import axios, { AxiosError } from 'axios';

export function getApiErrorMessage(error: unknown, fallback = 'API 요청에 실패했습니다.'): string {
  if (axios.isCancel(error)) return '요청이 취소되었습니다.';
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (error.response?.status) return `API 요청 실패 (${error.response.status})`;
    if (error.message) return error.message;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
