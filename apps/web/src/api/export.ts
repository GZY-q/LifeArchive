import { ApiError, request } from './client';

export async function exportJournal(
  includeDeleted: boolean,
  csrfToken: string,
  signal: AbortSignal,
): Promise<Blob> {
  const blob = (await request('/journal-export', {
    method: 'POST',
    body: { include_deleted: includeDeleted },
    csrfToken,
    responseType: 'blob',
    accept: 'application/zip',
    timeoutMs: 45_000,
    signal,
  })) as Blob;
  if (
    blob.type !== 'application/zip' ||
    blob.size < 1 ||
    blob.size > 32 * 1024 * 1024
  )
    throw new ApiError(0, 'invalid_export');
  return blob;
}

export function exportError(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 413)
      return '档案超出网页导出上限，请使用命令行导出完整档案。';
    if (cause.status === 429) return '已有导出正在处理，请稍后重新生成。';
    if (cause.status === 504)
      return '生成导出文件超时，请重试；较大档案可使用命令行导出。';
    if (cause.status === 503)
      return '导出未完成，请检查服务和原图是否可用，再重新生成。';
    if (cause.status === 403) return '安全校验未通过，请重新验证登录后重试。';
  }
  return '尚未取得完整导出文件，请检查连接后重新生成。';
}
