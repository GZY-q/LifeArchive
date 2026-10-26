import { ApiError, invalidResponse, isRecord, request } from './client';

export type Asset = {
  id: string;
  mime_type: 'image/jpeg' | 'image/png' | 'image/webp';
  byte_size: number;
  sha256: string;
  width: number;
  height: number;
  created_at: string;
};

export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
export const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

export function assetFrom(value: unknown): Asset {
  if (
    !isRecord(value) ||
    typeof value.id !== 'string' ||
    typeof value.mime_type !== 'string' ||
    !IMAGE_TYPES.includes(value.mime_type) ||
    typeof value.sha256 !== 'string' ||
    !/^[a-f0-9]{64}$/.test(value.sha256) ||
    typeof value.created_at !== 'string' ||
    !Number.isFinite(Date.parse(value.created_at)) ||
    typeof value.byte_size !== 'number' ||
    !Number.isInteger(value.byte_size) ||
    value.byte_size < 1 ||
    value.byte_size > MAX_IMAGE_BYTES ||
    typeof value.width !== 'number' ||
    !Number.isInteger(value.width) ||
    value.width < 1 ||
    value.width > 20_000 ||
    typeof value.height !== 'number' ||
    !Number.isInteger(value.height) ||
    value.height < 1 ||
    value.height > 20_000 ||
    value.width * value.height > 20_000_000
  )
    return invalidResponse();
  return value as Asset;
}

export function assetsFrom(value: unknown): Asset[] {
  if (!Array.isArray(value) || value.length > 10) return invalidResponse();
  const assets = value.map(assetFrom);
  if (new Set(assets.map((asset) => asset.id)).size !== assets.length)
    return invalidResponse();
  return assets;
}

export async function uploadAsset(
  file: File,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<Asset> {
  return assetFrom(
    await request('/assets', {
      method: 'POST',
      rawBody: file,
      contentType: file.type,
      csrfToken,
      signal,
    }),
  );
}

export async function readAsset(
  asset: Asset,
  signal?: AbortSignal,
): Promise<Blob> {
  const blob = (await request(`/assets/${encodeURIComponent(asset.id)}`, {
    responseType: 'blob',
    signal,
  })) as Blob;
  if (blob.type !== asset.mime_type || blob.size !== asset.byte_size)
    throw new ApiError(0, 'invalid_image');
  return blob;
}

export function imageExtension(mime: Asset['mime_type']): string {
  return mime === 'image/jpeg' ? 'jpg' : mime === 'image/png' ? 'png' : 'webp';
}

export function imageError(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 413)
      return '图片超过单文件 5 MiB 或档案图片配额，请缩小图片后重试。';
    if (cause.status === 422)
      return '请使用完整、非动画的 JPEG、PNG 或 WebP 图片，最多 2,000 万像素。';
    if (cause.status === 404 || cause.status === 503)
      return '原图暂不可用，请稍后重试。';
    if (cause.status === 403) return '安全校验未通过，请重新验证登录后重试。';
  }
  return '图片处理尚未完成，请检查连接后重试；已选择的图片仍保留。';
}
