# 14 安全Markdown预览交接

范围见 [14工单](../tasks/14-markdown-preview.md)。分支`codex/markdown-preview`从`codex/account-security`的`41276cf8ef46d4d6a6aa4f571ead1c72efe92623`堆叠交付；不自动合并前序PR。07真实输入法矩阵仍待人工证据，本片不替换编辑器或宣称真机通过。

## 使用与运行

日记、历史、日期详情、往年今日、搜索、回收站与409最新版本默认显示原文，可点“预览 Markdown/查看原文”。编辑区“预览草稿/收起预览”在原输入框旁显示只读结果，输入框一直挂载；组合输入、保存、上传或禁用期间不切换，冻结创建请求仍可查看。预览不触发保存/查询或修订，不改原文换行、尾空格和Unicode。

支持标题、段落、强调、列表、引用、代码、分隔线，以及GFM表格、删除线和只读任务框。没有语法高亮/数学/Mermaid执行或外部渲染器。链接仅绝对HTTP/HTTPS、无凭据/控制字符；邮件、相对/协议相对、脚注跳转或危险协议为不可点击文字。Markdown图片仅alt占位，原图仍从现有私密图库展开查看。

已有实例从仓库根目录更新：

```bash
docker compose up -d --build --wait
```

没有后端、迁移、配置或导出变化，head仍0006、格式v4。前端新增两个精确依赖与锁文件，本机按锁安装：

```bash
cd apps/web
npm ci --registry=https://registry.npmmirror.com
npm run dev
```

默认Vite5173代理本机API8000，复用其他API时设置API_PROXY_TARGET，沿用根README。当前 [18088开发预览](http://127.0.0.1:18088/)已加载新模块（HTTP200），无需改密、改数据库或重启API；原图/凭据/数据保留。私密启动说明在`/Users/gede/.cache/lifearchive-tags-dev-qockdezn/HANDOFF.md`。本轮未build或覆盖旧dist，18086输入法环境保持原版。

## 依赖与安全边界

- `react-markdown@10.1.0`、`remark-gfm@4.0.1`精确锁定，实际安装license均MIT；前者React/@types peer>=18，兼容本仓库React19。经锁文件对比，旧有包版本未变，只有新增依赖及dev标记调整。依据：[react-markdown](https://github.com/remarkjs/react-markdown)、[remark-gfm](https://github.com/remarkjs/remark-gfm)。
- `components/MarkdownPreview.tsx`：skipHtml、固定允许元素/组件，不安装rehype-raw、不使用innerHTML，不透传AST node或任意属性。用标准URL解析与小范围协议策略，不自己解析Markdown。外链新页noopener/noreferrer/no-referrer，HTML/代码不执行。`input`强制disabled/readOnly。
- img组件只返回纯文字alt占位、urlTransform不放行src，不生成img/srcset或请求；私密AssetGallery鉴权策略不变。这是受限Markdown渲染器，不是通用HTML清洗器，不应以后随意接入raw插件。
- `components/MarkdownContent.tsx`：本地原文/预览状态，默认pre.markdown-text，按钮type=button。预览只在开启后挂载，useDeferredValue避免优先阻塞键入；没有大规模100k长文性能承诺。
- `components/markdown.css`：局部排版/代码/表格滚动；各读取入口共用组件。`EntryForm`保留现MarkdownEditor与textarea节点、图片/标签/冻结UUID/409逻辑，不写API或持久化显示偏好。

## 必要验证

按用户要求减少测试、功能优先，仅执行：

- `src/components/MarkdownPreview.test.tsx`3项通过：CommonMark/GFM/只读任务框，活动HTML/危险URL/远程图片无活动节点，原文CRLF/尾空格/Unicode及切换不提交/请求。URL控制字符补强后仅复核这3项，最终通过（370毫秒总耗时）。
- `src/journal/MarkdownPreview.test.tsx`2项通过（1.01秒）：同textarea节点、组合输入锁、导航/图片/冻结完整请求与UUID、409读取/显式rebase，切换无PATCH。
- typecheck、lint、修改文件Prettier与diff通过；Vite新预览模块HTTP200。没有运行本机全量回归、build、浏览器/恢复/真机演练，不以13的CI替代本片验收。

最小复核：

```bash
cd apps/web
npm run typecheck
npm run lint
npm test -- --run src/components/MarkdownPreview.test.tsx src/journal/MarkdownPreview.test.tsx
```

## 下一片建议

15建议标签改名：先明确唯一性/并发、ID稳定、历史名称快照不回写、目录和已提交筛选摘要刷新；不改Markdown、不删除关联或历史。标签/媒体永久清除需要独立保留策略，不能顺手加入。低成本模型接手复用当前渲染器、图库和草稿边界，不重搭编辑器或调用外部AI。
