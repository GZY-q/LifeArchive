# 14 — 安全Markdown只读预览

继续13交接规划，以子代理推进功能、减少测试；从`codex/account-security`的`41276cf8ef46d4d6a6aa4f571ead1c72efe92623`堆叠交付，不自行合并。保留用户`.DS_Store`、预览数据/凭据/原图与18086输入法环境；07真实矩阵仍待证据。

## 功能和固定边界

- 仅前端，新增`react-markdown@10.1.0`与`remark-gfm@4.0.1`精确版本及锁文件；两者MIT，已核验react-markdown React/@types peer>=18，复用现有React19。优先大陆镜像，不升级其他依赖。
- 共用`MarkdownPreview`组件：标题、段落、强调、引用、列表、行内/围栏代码、分隔线，以及GFM表格/删除线/只读任务列表。默认无语法高亮服务/数学/Mermaid/远程渲染器，不执行代码。
- 强制skipHtml，不安装rehype-raw、不使用dangerouslySetInnerHTML/innerHTML，不允许script/style/iframe/object/embed等活动元素。链接经自有小范围URL策略，只允许无凭据、无控制字符的绝对http/https；相对/协议相对/mailto/javascript/data/blob/file等降为非链接文字。安全外链新页打开，noopener+noreferrer、referrerPolicy=no-referrer。
- Markdown图片一律不创建img，不读取src/srcset，不发请求；渲染纯文字alt占位并提示使用私密图库，原有AssetGallery保持独立鉴权按需读取。HTML中的图片/视频/音频/链接不启用。
- URL策略用标准URL解析，不自写Markdown解析器；不向DOM透传AST node或任意属性，GFM checkbox强制disabled/readOnly。固定允许元素/组件，不让插件引入任意富HTML。原始Markdown始终由React文本节点显示，不因预览改写换行/空格/Unicode或数据。

## 接入

- `MarkdownContent`（或同责小组件）默认原文pre，提供本地“预览Markdown/查看原文”切换。日记、修订历史、日期详情、往年今日、归档搜索、回收站及409最新版本复用；默认原文维持现有阅读和测试语义。标识、标签、私密图片和操作区域不改变。
- 编辑区添加“预览草稿/收起预览”，只打开时渲染当前草稿；textarea一直挂载，仍是现MarkdownEditor，不用切key/卸载/替换contentEditable，不重构IME适配。组合输入/保存/上传/禁用期间不切换，现有保存与冲突逻辑不变；冻结创建请求仍可只读预览，不改草稿/UUID。
- 预览本地懒挂载，可用useDeferredValue减轻键入时渲染；不做外部请求/存储，不声称100k长文已大规模性能验收。所有按钮type=button，不触发提交。原文/预览切换不读写API或触发修订。
- 跨视图/401/密码轮换、原文草稿、图片选择、创建请求冻结与409保护保持；不持久化预览偏好，不改搜索/列表排序。

## 排除与交付

无后端/API/迁移/配置/导出变化，head仍0006、格式仍v4；无新闻/AI、图表执行、外部媒体、编辑器替换。代码+少量关键安全/状态测试+依赖/安全/运行/交接文档和独立PR；只做必要typecheck/lint/锁依赖与少量新用例，不做全量/浏览器/恢复演练。

预览继续18088，安装依赖触发Vite更新即可，不build或改旧dist，不动18086，不替owner改密/撤销会话。下一片只规划。
