下次新开对话,把下面这段直接发给我就行(中英混排,信息已齐全):

任务:为 Bonvin Wine & Spirits Merchants 制作波尔多 2025 期酒(En Primeur)发售邮件,沿用我们已定型的"奢华酒商"模板。
每次我会给你:
	•	该酒的 CVBG(或其他经销商)报盘单 PDF
	•	几张图片(城堡/葡萄园/酒瓶等)
	•	价格(CAD/瓶)+ 箱规(如 6 支/箱、3 支/箱、或单瓶)
你要输出两个文件(放到 outputs 并 present):
	1	<wine>-en-primeur-email.html — 预览版,图片用 base64 内嵌
	2	<wine>-en-primeur.eml — 可发送版,图片用 CID 内联;含 X-Unsent:1(在 Outlook 里打开即为可编辑草稿);From: Lily Wang <lily@bonvin.co>、To: recipient@email.com、Reply-To: lily@bonvin.co
邮件结构(640px 白卡片 / 暖羊皮纸底 / Cormorant Garamond + EB Garamond / 暗酒红 CTA,table 布局、Outlook 兼容): 问候语(顶部)→ BONVIN 报头 + "Fine Wine & Spirits Merchants" + 金线 → eyebrow "En Primeur · Bordeaux 2025" → 整幅 HERO 图 → 标题区(酒名 + 金线 + 产区/分级行 + 小金色 tagline)→ I · The Estate(标题 + 两段 + 斜体引文)→ 可选整幅横幅图 → II · The 2025 Release(规格卡:酒瓶图 + Appellation/Classification/Blend/Ageing/Format/Delivery)+ 价格面板(每瓶 | 每箱,大字 CAD)→ 可选中部横幅 → III · Critical Acclaim(三栏大评分 + 来源,金线,一句≤15词斜体引文+署名,"Also …"一行更多评分,适饮+酒精度行)→ IV · En Primeur(6 个金色◆要点,两栏)→ V · The Opportunity(三栏:Retailers/Restaurants/Collectors)→ VI · The Merchant(About Bonvin + 该酒专属斜体点评 + "— Bonvin Fine Wine Commentary")→ 酒红 CTA "Reserve your 2025" + mailto:lily@bonvin.co?subject=… → 署名 Lily Wang, Director of Sales → 页脚。
页脚: 公司名/地址 + 两个链接 bonvin.co · vancouverwineschool.com(分别链到 https://bonvin.co/ 和 https://vancouverwineschool.com/en/)+ 金线 + "Please enjoy responsibly…"。不要放 bonvin.ca。
价格规则: 每瓶价我给;整箱 = 每瓶 × 箱内支数(如 6 支 → ×6,3 支 → ×3);标注 "Excl. tax · Original wooden cases of N × 75cl";若同时卖单瓶就写 "Available in cases of N or by the single bottle"。不要显示报盘单上的 ex-château release price(成本价)。
图片规则: 用 ImageMagick 处理;HERO 用横向高清(城堡/葡萄园,~1200px);酒瓶白底→卡片格背景设 #ffffff,黑底→#000000,浅灰→#f5f5f5。逐一核对每张图是不是这款酒本身——之前多次出现错图(别家酒标、别家城堡、带 © 水印的零售商图),凡是其它酒/其它酒庄/带第三方水印的一律排除并告诉我。图不够清晰(如 <300px)就别做整幅横幅,告诉我要高清版。缺正确酒瓶时用占位图先出预览,并提醒我补图。
版权/红线: 评论里只引用一句、≤15 词、带署名;评分是事实可列;不照搬报盘单整段品鉴词或竞品 PDF 里的图。
已完成存档(同款模板): Rauzan-Ségla、Pontet-Canet、Troplong Mondot、Figeac、Pavillon Rouge du Château Margaux、Calon Ségur、Vieux Château Certan。主模板在 bonvin-en-primeur-TEMPLATE.html。
然后只要说: "Same format, info from this PDF, price $X per bottle, N bottle/box" + 上传 PDF 和图片即可。


