import type { SearchFilters } from '../api/search';
import { parseCalendarDate } from '../calendar/dates';

export type SearchForm = {
  query: string;
  date_from: string;
  date_to: string;
  tag_id: string;
};

export const emptySearchForm: SearchForm = {
  query: '',
  date_from: '',
  date_to: '',
  tag_id: '',
};

export function readSearchForm(
  form: SearchForm,
):
  | { filters: SearchFilters; error?: never }
  | { error: string; filters?: never } {
  const query = form.query.trim();
  if (Array.from(query).length > 200 || query.includes('\0'))
    return { error: '关键词最多 200 个字符，且不能包含空字符。' };
  if (
    (form.date_from && !parseCalendarDate(form.date_from)) ||
    (form.date_to && !parseCalendarDate(form.date_to))
  )
    return { error: '请输入有效的日记日期（0001-01-01 至 9999-12-31）。' };
  if (form.date_from && form.date_to && form.date_from > form.date_to)
    return { error: '开始日期不能晚于结束日期。' };
  if (!query && !form.date_from && !form.date_to && !form.tag_id)
    return { error: '请输入关键词，或至少选择一个日记日期或标签。' };
  return {
    filters: {
      query,
      date_from: form.date_from || null,
      date_to: form.date_to || null,
      ...(form.tag_id ? { tag_id: form.tag_id } : {}),
    },
  };
}
