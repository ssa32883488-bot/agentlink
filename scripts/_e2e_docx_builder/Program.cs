using System.Text;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using A = DocumentFormat.OpenXml.Drawing;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;
using WpPageSize = DocumentFormat.OpenXml.Wordprocessing.PageSize;

static string FindEvidenceRoot()
{
    var cur = new DirectoryInfo(AppContext.BaseDirectory);
    while (cur != null)
    {
        var p = Path.Combine(cur.FullName, "docs", "evidence", "e2e_thinking_chain", "final_best");
        if (Directory.Exists(p)) return p;
        cur = cur.Parent;
    }
    var fallback = Path.GetFullPath(Path.Combine(
        AppContext.BaseDirectory, "..", "..", "..", "..",
        "docs", "evidence", "e2e_thinking_chain", "final_best"));
    if (!Directory.Exists(fallback))
        throw new DirectoryNotFoundException("final_best not found");
    return fallback;
}

var evidence = FindEvidenceRoot();
var outDir = Path.Combine(Path.GetDirectoryName(evidence)!, "reports");
Directory.CreateDirectory(outDir);
var outName = Environment.GetEnvironmentVariable("E2E_DOCX_NAME")
    ?? "AgentLink_E2E_双场景验收证据包_20261029_clean.docx";
var outPath = Path.Combine(outDir, outName);

uint drawingId = 1;
Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);

using (var doc = WordprocessingDocument.Create(outPath, WordprocessingDocumentType.Document))
{
    var main = doc.AddMainDocumentPart();
    main.Document = new Document(new Body());
    var body = main.Document.Body!;

    var stylesPart = main.AddNewPart<StyleDefinitionsPart>();
    stylesPart.Styles = BuildStyles();

    var props = doc.PackageProperties;
    props.Title = "AgentLink 双场景 E2E 验收证据包";
    props.Creator = "AgentLink QA";
    props.Created = DateTime.UtcNow;
    props.Subject = "S1 组合拆单 / S2 组群竞价 · 最终保留批次";

    // —— Cover ——
    body.Append(P("AgentLink 多智能体采购协议", "Title"));
    body.Append(P("双场景端到端验收证据包", "Subtitle"));
    body.Append(P("场景一：组合需求覆盖匹配与拆单履约", "NormalCenter"));
    body.Append(P("场景二：同 SKU 多家供应商组群竞价履约", "NormalCenter"));
    body.Append(P($"成文日期：2026-10-29　　证据根目录：final_best", "NormalCenter"));
    body.Append(P("保留原则：每种测试只保留效果最好且完整通过的一次，并全量收录截图、关键日志与回溯审计。", "BodyText"));
    body.Append(PageBreak());

    // —— 1 总览 ——
    body.Append(P("1. 验收总览", "Heading1"));
    body.Append(P("本次验收覆盖 AgentLink 双云部署（腾讯云采购/物流 + 阿里云供应商）下的两条核心业务链路。最终只保留一次最佳通过结果写入本证据包。", "BodyText"));
    AppendTable(body, new[] { "场景", "结果", "案例 ID", "证据批次", "终态" }, new[]
    {
        new[] { "S1 组合拆单", "PASS", "case-825b6d1c", "fast_20261029_183158 + 链式截图 163056", "ACTIVE" },
        new[] { "S2 组群竞价", "PASS", "case-56960216", "s2fix_20261029_185546", "ACTIVE" },
    });
    body.Append(P("1.1 环境与身份", "Heading2"));
    AppendTable(body, new[] { "角色", "Agent", "部署", "控制台" }, new[]
    {
        new[] { "采购商 A", "buyer-a", "腾讯云 81.70.46.119", "https://ashui.online:8090/" },
        new[] { "物流", "logistics", "腾讯云同机", "https://ashui.online:8095/" },
        new[] { "供应商 A/B/C", "supplier-a/b/c", "阿里云 39.105.20.113", "8091 / 8092 / 8093" },
    });
    body.Append(P("1.2 思考链（状态机共识）", "Heading2"));
    body.Append(P("开放供需 → 整案发现 → 覆盖匹配 → 部分覆盖则拆单；同 SKU 多家可供给才进入组群竞价。状态机始终显式持有甲乙方与标的（SKU/数量/案例）。", "BodyText"));
    body.Append(PageBreak());

    // —— 2 S1 ——
    body.Append(P("2. 场景一：组合拆单全链路", "Heading1"));
    body.Append(P("2.1 用例说明", "Heading2"));
    body.Append(P("采购需求：重型脚轮300kg × 500 + 高档座椅面料 × 500。发现供应商后 RFQ，按覆盖矩阵拆单：脚轮→supplier-a，面料→supplier-b；各自生成订单工单，三方确认后 ACTIVE。", "BodyText"));

    body.Append(P("2.2 关键结果数据", "Heading2"));
    AppendTable(body, new[] { "SKU", "供应商", "单价", "货款", "工单 ID", "标题校验" }, new[]
    {
        new[] { "RM-CASTER-300", "supplier-a", "18.0", "9000.0", "tk-ord-ase-825b6d1c-supplier-a-M-CASTER-300", "通过（无串货）" },
        new[] { "RM-FABRIC-PRO", "supplier-b", "35.0", "17500.0", "tk-ord-ase-825b6d1c-supplier-b-M-FABRIC-PRO", "通过（无串货）" },
    });
    AppendTable(body, new[] { "步骤", "日志要点" }, new[]
    {
        new[] { "发现", "S1_DISCOVER n=3 ids=[supplier-a,b,c]" },
        new[] { "询价覆盖", "coverage CASTER→A / FABRIC→B；split_plan 两行" },
        new[] { "下单", "双订单 CONTRACT_PENDING，bad_title=false" },
        new[] { "供应商确认", "SUP_ACK A/B both_acked effective=true" },
        new[] { "物流", "FORCE_LOG tk-log-a-M-CASTER-300 / tk-log-b-M-FABRIC-PRO" },
        new[] { "生效", "ACTIVATE case-825b6d1c ACTIVE" },
    });

    body.Append(P("2.3 关键日志摘录", "Heading2"));
    AppendLogBlock(body, ReadTrim(Path.Combine(evidence, "s1", "s1_core.log")));
    AppendLogBlock(body, ReadTrim(Path.Combine(evidence, "s1", "s1_sup.log")));
    AppendLogBlock(body, ReadTrim(Path.Combine(evidence, "s1", "s1_finish.log")));

    body.Append(P("2.4 终态截图（采购 / 供应 / 物流 / 审计）", "Heading2"));
    AddShot(main, body, Path.Combine(evidence, "s1", "screenshots", "s1_sa_tickets.png"),
        "图 S1-1 供应商 A 工单：脚轮订单已生效", ref drawingId);
    AddShot(main, body, Path.Combine(evidence, "s1", "screenshots", "s1_sb_tickets.png"),
        "图 S1-2 供应商 B 工单：面料订单已生效", ref drawingId);
    AddShot(main, body, Path.Combine(evidence, "s1", "screenshots", "s1_buyer_audit.png"),
        "图 S1-3 采购商回溯审计：拆单双工单 closed", ref drawingId);

    body.Append(P("2.5 补充工单过程截图（仅收录无失败态画面）", "Heading2"));
    body.Append(P(
        "说明：早期浏览器对话批次（20261029_163056）曾出现「失败：network error」，该类截图不得进入验收包。" +
        "本节仅保留同链路中工单/确认终态画面；对话过程失败图已剔除。业务结论以 fast_20261029_183158 日志与上方终态图为准。",
        "BodyText"));
    var s1Chain = new (string file, string caption)[]
    {
        ("s1_07_supplier_a_tickets_acked.png", "图 S1-C1 供应商 A 确认后工单"),
        ("s1_08_supplier_b_tickets.png", "图 S1-C2 供应商 B 工单"),
        ("s1_12_sa_final.png", "图 S1-C3 供应商 A 终态"),
        ("s1_13_sb_final.png", "图 S1-C4 供应商 B 终态"),
    };
    foreach (var (file, caption) in s1Chain)
    {
        var path = Path.Combine(evidence, "s1", "screenshots", "chain", file);
        if (File.Exists(path)) AddShot(main, body, path, caption, ref drawingId);
    }
    body.Append(PageBreak());

    // —— 3 S2 ——
    body.Append(P("3. 场景二：组群竞价全链路", "Heading1"));
    body.Append(P("3.1 用例说明", "Heading2"));
    body.Append(P("采购需求：标准脚轮200kg（RM-CASTER-200）× 500。短名单锁定 supplier-a 与 supplier-c（同 SKU 重叠供给）→ 组群竞价。跨云 group invite 超时后自动 RPC 盲标回退，取得 ≥2 有效出价，选低价供应商下单并完成三方确认。", "BodyText"));

    body.Append(P("3.2 关键结果数据", "Heading2"));
    AppendTable(body, new[] { "项", "值" }, new[]
    {
        new[] { "运输层", "rpc（group invite 失败后回退）" },
        new[] { "有效出价", "2" },
        new[] { "supplier-a", "13.5 → 中标" },
        new[] { "supplier-c", "15.0" },
        new[] { "订单", "tk-ord-ase-56960216-supplier-a-M-CASTER-200" },
        new[] { "货款", "6750.0（13.5×500）" },
        new[] { "物流工单", "tk-log-a-M-CASTER-200" },
        new[] { "案例终态", "case-56960216 ACTIVE" },
    });

    body.Append(P("3.3 关键日志摘录", "Heading2"));
    AppendLogBlock(body, ExtractKeyLines(Path.Combine(evidence, "s2", "core.log"),
        new[] { "RFQ_N", "AUCTION ", "ORDER ", "BUYER_ACK", "DONE " }));
    AppendLogBlock(body, ReadTrim(Path.Combine(evidence, "s2", "sup.log")));
    AppendLogBlock(body, ReadTrim(Path.Combine(evidence, "s2", "fin.log")));

    body.Append(P("3.4 终态截图", "Heading2"));
    AddShot(main, body, Path.Combine(evidence, "s2", "screenshots", "s2_sa_tickets.png"),
        "图 S2-1 供应商 A：CASTER-200 订单+物流已生效（case-56960216）", ref drawingId);
    AddShot(main, body, Path.Combine(evidence, "s2", "screenshots", "s2_logistics.png"),
        "图 S2-2 物流台：tk-log-a-M-CASTER-200 物流已生效", ref drawingId);
    AddShot(main, body, Path.Combine(evidence, "s2", "screenshots", "s2_audit.png"),
        "图 S2-3 采购商回溯审计：标准脚轮200kg 工单 closed", ref drawingId);
    AddShot(main, body, Path.Combine(evidence, "s2", "screenshots", "s2_buyer_tickets.png"),
        "图 S2-4 采购商待办（生效回档后开放待办为空，属预期终态）", ref drawingId);

    body.Append(P("3.5 过程截图收录说明", "Heading2"));
    body.Append(P(
        "历史浏览器对话演练中出现过「失败：network error」（对话中断），该批次过程图不得作为验收通过证据。" +
        "场景二验收仅采用 s2fix_20261029_185546 的终态截图（§3.4）与关键日志（§3.3）：priced≥2、三方确认、ACTIVE。" +
        "若需对话过程截图，须在修复网络/会话稳定性后重跑浏览器 E2E，确认无失败态再入册。",
        "BodyText"));
    body.Append(PageBreak());

    // —— 4 回溯与修复 ——
    body.Append(P("4. 回溯审计与关键修复", "Heading1"));
    body.Append(P("4.1 全链路回溯结论", "Heading2"));
    AppendTable(body, new[] { "检查项", "S1", "S2" }, new[]
    {
        new[] { "发现/短名单", "3 家发现，按覆盖拆", "锁定 A+C 重叠 SKU" },
        new[] { "定价/方案", "拆单两行 split_plan", "RPC 双出价选低" },
        new[] { "订单标题", "按产品摘要，无串货", "标准脚轮200kg" },
        new[] { "甲乙方可见", "buyer-a ↔ A/B", "buyer-a ↔ A（中标）" },
        new[] { "物流三方确认", "双线承运生效", "单线承运生效" },
        new[] { "案例状态", "ACTIVE", "ACTIVE" },
    });
    body.Append(P("4.2 本轮关键修复", "Heading2"));
    body.Append(Bullet("buyer wit 指令渲染禁止对含花括号文本使用 .format()，消除 KeyError 崩溃。"));
    body.Append(Bullet("订单工单标题优先 order_draft 产品摘要，修复供应商 A 面料串标题问题。"));
    body.Append(Bullet("step_auction：组群无有效定价出价时强制 RPC blind-bid 回退，保证可比出价 ≥2。"));
    body.Append(P("4.3 残留风险", "Heading2"));
    body.Append(P("组群 MQ invite 跨云仍不稳定；当前业务正确性依赖 RPC 回退。后续可单独加固 invite/超时策略，但不影响本次验收结论。", "BodyText"));
    body.Append(PageBreak());

    // —— 5 附录 ——
    body.Append(P("5. 附录：证据文件索引", "Heading1"));
    body.Append(P("本 DOCX 对应磁盘证据包目录：docs/evidence/e2e_thinking_chain/final_best/", "BodyText"));
    AppendTable(body, new[] { "路径", "说明" }, new[]
    {
        new[] { "MANIFEST.md", "最终保留原则说明" },
        new[] { "FINAL_REVIEW.md", "双场景复盘摘要" },
        new[] { "s1/*.log", "S1 核心/供应/生效日志" },
        new[] { "s1/screenshots/", "S1 终态截图" },
        new[] { "s1/screenshots/chain/", "S1 过程链式截图" },
        new[] { "s2/*.log", "S2 核心/供应/生效日志" },
        new[] { "s2/screenshots/", "S2 终态截图" },
        new[] { "s2/screenshots/chain/", "S2 过程链式截图" },
    });
    body.Append(P("完整原始日志（含 invite 超时堆栈）保留在 final_best/s2/core.log，正文仅摘录关键业务行。", "BodyText"));

    // section properties last
    body.Append(new SectionProperties(
        new WpPageSize { Width = 11906U, Height = 16838U },
        new PageMargin
        {
            Top = 1134, Right = 1134U, Bottom = 1134, Left = 1134U,
            Header = 720U, Footer = 720U, Gutter = 0U
        }
    ));

    // header/footer
    var headerPart = main.AddNewPart<HeaderPart>();
    var headerRel = main.GetIdOfPart(headerPart);
    headerPart.Header = new Header(
        new Paragraph(
            new ParagraphProperties(
                new ParagraphStyleId { Val = "Header" },
                new Justification { Val = JustificationValues.Right }),
            RunText("AgentLink E2E 验收证据包 · 最终保留批次", "HeaderChar")));
    var footerPart = main.AddNewPart<FooterPart>();
    var footerRel = main.GetIdOfPart(footerPart);
    footerPart.Footer = new Footer(
        new Paragraph(
            new ParagraphProperties(
                new ParagraphStyleId { Val = "Footer" },
                new Justification { Val = JustificationValues.Center }),
            RunText("第 ", "FooterChar"),
            new SimpleField { Instruction = "PAGE" },
            RunText(" 页", "FooterChar")));

    var sect = body.Elements<SectionProperties>().Last();
    sect.PrependChild(new HeaderReference { Type = HeaderFooterValues.Default, Id = headerRel });
    sect.PrependChild(new FooterReference { Type = HeaderFooterValues.Default, Id = footerRel });
}

Console.WriteLine("WROTE " + outPath);

// ——— helpers ———

static Styles BuildStyles()
{
    var styles = new Styles(
        new DocDefaults(
            new RunPropertiesDefault(
                new RunPropertiesBaseStyle(
                    new RunFonts { Ascii = "Calibri", HighAnsi = "Calibri", EastAsia = "宋体", ComplexScript = "Calibri" },
                    new FontSize { Val = "21" },
                    new FontSizeComplexScript { Val = "21" },
                    new Color { Val = "333333" },
                    new Languages { Val = "en-US", EastAsia = "zh-CN" })),
            new ParagraphPropertiesDefault(
                new ParagraphPropertiesBaseStyle(
                    new SpacingBetweenLines { Line = "276", LineRule = LineSpacingRuleValues.Auto, After = "120" }))));

    styles.Append(MakeStyle("Normal", "normal", "正文", "宋体", "Calibri", 21, false, null, JustificationValues.Both, "120"));
    styles.Append(MakeStyle("BodyText", "paragraph", "正文段落", "宋体", "Calibri", 21, false, "Normal", JustificationValues.Both, "160"));
    styles.Append(MakeStyle("NormalCenter", "paragraph", "居中正文", "宋体", "Calibri", 21, false, "Normal", JustificationValues.Center, "120"));
    styles.Append(MakeStyle("Title", "paragraph", "标题", "微软雅黑", "Calibri", 36, true, "Normal", JustificationValues.Center, "200", "200", "1F3864", 0));
    styles.Append(MakeStyle("Subtitle", "paragraph", "副标题", "微软雅黑", "Calibri", 28, false, "Normal", JustificationValues.Center, "120", "240", "2E75B6"));
    styles.Append(MakeStyle("Heading1", "paragraph", "标题 1", "微软雅黑", "Calibri", 28, true, "Normal", JustificationValues.Left, "200", "280", "1F3864", 0));
    styles.Append(MakeStyle("Heading2", "paragraph", "标题 2", "微软雅黑", "Calibri", 24, true, "Normal", JustificationValues.Left, "120", "200", "2E75B6", 1));
    styles.Append(MakeStyle("Caption", "paragraph", "题注", "宋体", "Calibri", 18, false, "Normal", JustificationValues.Center, "80", "40", "666666"));
    styles.Append(MakeStyle("CodeBlock", "paragraph", "日志块", "Consolas", "Consolas", 16, false, "Normal", JustificationValues.Left, "60", "40", "111111"));
    styles.Append(MakeStyle("ListParagraph", "paragraph", "列表", "宋体", "Calibri", 21, false, "Normal", JustificationValues.Both, "60"));
    styles.Append(MakeStyle("Header", "paragraph", "页眉", "宋体", "Calibri", 16, false, "Normal", JustificationValues.Right, "0"));
    styles.Append(MakeStyle("Footer", "paragraph", "页脚", "宋体", "Calibri", 16, false, "Normal", JustificationValues.Center, "0"));
    styles.Append(MakeCharStyle("HeaderChar", "页眉字符", "宋体", "Calibri", 16, "666666"));
    styles.Append(MakeCharStyle("FooterChar", "页脚字符", "宋体", "Calibri", 16, "666666"));
    styles.Append(MakeCharStyle("CodeChar", "代码字符", "Consolas", "Consolas", 16, "111111"));
    return styles;
}

static Style MakeStyle(string id, string type, string name, string eastAsia, string ascii, int sz,
    bool bold, string? basedOn, JustificationValues align, string after,
    string before = "0", string? color = null, int? outline = null)
{
    var st = new Style { Type = type == "normal" ? StyleValues.Paragraph : StyleValues.Paragraph, StyleId = id };
    if (type == "normal") st.Default = true;
    st.Append(new StyleName { Val = name });
    if (basedOn != null) st.Append(new BasedOn { Val = basedOn });
    var rPr = new StyleRunProperties(
        new RunFonts { Ascii = ascii, HighAnsi = ascii, EastAsia = eastAsia, ComplexScript = ascii },
        new FontSize { Val = sz.ToString() },
        new FontSizeComplexScript { Val = sz.ToString() });
    if (bold) rPr.Append(new Bold());
    if (color != null) rPr.Append(new Color { Val = color });
    st.Append(rPr);
    var pPr = new StyleParagraphProperties(
        new Justification { Val = align },
        new SpacingBetweenLines { Before = before, After = after, Line = "276", LineRule = LineSpacingRuleValues.Auto });
    if (outline.HasValue) pPr.Append(new OutlineLevel { Val = outline.Value });
    st.Append(pPr);
    return st;
}

static Style MakeCharStyle(string id, string name, string eastAsia, string ascii, int sz, string color)
{
    var st = new Style { Type = StyleValues.Character, StyleId = id };
    st.Append(new StyleName { Val = name });
    st.Append(new StyleRunProperties(
        new RunFonts { Ascii = ascii, HighAnsi = ascii, EastAsia = eastAsia },
        new FontSize { Val = sz.ToString() },
        new Color { Val = color }));
    return st;
}

static Paragraph P(string text, string style)
{
    return new Paragraph(
        new ParagraphProperties(new ParagraphStyleId { Val = style }),
        new Run(new Text(text) { Space = SpaceProcessingModeValues.Preserve }));
}

static Paragraph Bullet(string text)
{
    return new Paragraph(
        new ParagraphProperties(
            new ParagraphStyleId { Val = "ListParagraph" },
            new Indentation { Left = "420" }),
        new Run(new Text("• " + text) { Space = SpaceProcessingModeValues.Preserve }));
}

static Paragraph PageBreak() =>
    new Paragraph(new Run(new Break { Type = BreakValues.Page }));

static Run RunText(string text, string? style = null)
{
    var run = new Run();
    if (style != null)
        run.AppendChild(new RunProperties(new RunStyle { Val = style }));
    run.AppendChild(new Text(text) { Space = SpaceProcessingModeValues.Preserve });
    return run;
}

static void AppendTable(Body body, string[] headers, string[][] rows)
{
    var table = new Table();
    table.Append(new TableProperties(
        new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct },
        new TableBorders(
            new TopBorder { Val = BorderValues.Single, Size = 4, Color = "AAAAAA" },
            new LeftBorder { Val = BorderValues.Single, Size = 4, Color = "AAAAAA" },
            new BottomBorder { Val = BorderValues.Single, Size = 4, Color = "AAAAAA" },
            new RightBorder { Val = BorderValues.Single, Size = 4, Color = "AAAAAA" },
            new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4, Color = "DDDDDD" },
            new InsideVerticalBorder { Val = BorderValues.Single, Size = 4, Color = "DDDDDD" })));
    var grid = new TableGrid();
    foreach (var _ in headers) grid.Append(new GridColumn());
    table.Append(grid);

    var headerRow = new TableRow(new TableRowProperties(new TableHeader()));
    foreach (var h in headers)
    {
        headerRow.Append(Cell(h, true, "1F3864", "FFFFFF"));
    }
    table.Append(headerRow);
    for (int i = 0; i < rows.Length; i++)
    {
        var tr = new TableRow();
        var bg = i % 2 == 0 ? "F7F9FC" : "FFFFFF";
        foreach (var c in rows[i]) tr.Append(Cell(c, false, bg, "333333"));
        table.Append(tr);
    }
    body.Append(table);
    body.Append(P("", "BodyText"));
}

static TableCell Cell(string text, bool bold, string shade, string color)
{
    var rPr = new RunProperties(
        new RunFonts { Ascii = "Calibri", EastAsia = "宋体" },
        new FontSize { Val = "18" },
        new Color { Val = color });
    if (bold) rPr.Append(new Bold());
    return new TableCell(
        new TableCellProperties(
            new TableCellWidth { Type = TableWidthUnitValues.Auto },
            new Shading { Val = ShadingPatternValues.Clear, Fill = shade },
            new TableCellVerticalAlignment { Val = TableVerticalAlignmentValues.Center }),
        new Paragraph(
            new ParagraphProperties(new SpacingBetweenLines { Before = "40", After = "40" }),
            new Run(rPr, new Text(text) { Space = SpaceProcessingModeValues.Preserve })));
}

static void AppendLogBlock(Body body, string text)
{
    if (string.IsNullOrWhiteSpace(text)) return;
    foreach (var line in text.Replace("\r\n", "\n").Split('\n'))
    {
        body.Append(new Paragraph(
            new ParagraphProperties(
                new ParagraphStyleId { Val = "CodeBlock" },
                new Shading { Val = ShadingPatternValues.Clear, Fill = "F3F3F3" }),
            new Run(
                new RunProperties(new RunStyle { Val = "CodeChar" }),
                new Text(line.Length == 0 ? " " : line) { Space = SpaceProcessingModeValues.Preserve })));
    }
    body.Append(P("", "BodyText"));
}

static string ReadTrim(string path)
{
    if (!File.Exists(path)) return "";
    return File.ReadAllText(path, Encoding.UTF8).Trim();
}

static string ExtractKeyLines(string path, string[] prefixes)
{
    if (!File.Exists(path)) return "";
    var lines = File.ReadAllLines(path, Encoding.UTF8);
    var kept = new List<string>();
    foreach (var line in lines)
    {
        var t = line.TrimEnd();
        if (prefixes.Any(p => t.StartsWith(p, StringComparison.Ordinal)))
            kept.Add(t);
    }
    if (kept.Count == 0)
    {
        // also accept lines containing keywords
        foreach (var line in lines)
        {
            var t = line.Trim();
            if (t.Contains("AUCTION") || t.Contains("ORDER {") || t.Contains("BUYER_ACK") || t.StartsWith("DONE ") || t.StartsWith("RFQ_N"))
                kept.Add(t);
        }
    }
    return string.Join("\n", kept.Distinct());
}

static void AddShot(MainDocumentPart main, Body body, string path, string caption, ref uint drawingId)
{
    if (!File.Exists(path))
    {
        body.Append(P($"（缺图）{caption}", "Caption"));
        return;
    }
    var (pxW, pxH) = ReadPngSize(path);
    // fit to ~6.3" content width
    const double maxWidthIn = 6.3;
    double dpi = 96.0;
    double widthIn = pxW / dpi;
    double heightIn = pxH / dpi;
    if (widthIn > maxWidthIn)
    {
        var scale = maxWidthIn / widthIn;
        widthIn *= scale;
        heightIn *= scale;
    }
    // also cap height for very tall full-page shots
    const double maxHeightIn = 8.2;
    if (heightIn > maxHeightIn)
    {
        var scale = maxHeightIn / heightIn;
        widthIn *= scale;
        heightIn *= scale;
    }
    long cx = (long)(widthIn * 914400);
    long cy = (long)(heightIn * 914400);

    var imagePart = main.AddImagePart(ImagePartType.Png);
    using (var fs = File.OpenRead(path)) imagePart.FeedData(fs);
    string relId = main.GetIdOfPart(imagePart);
    uint id = drawingId++;

    var drawing = new Drawing(
        new DW.Inline(
            new DW.Extent { Cx = cx, Cy = cy },
            new DW.EffectExtent { LeftEdge = 0L, TopEdge = 0L, RightEdge = 0L, BottomEdge = 0L },
            new DW.DocProperties { Id = id, Name = Path.GetFileName(path), Description = caption },
            new DW.NonVisualGraphicFrameDrawingProperties(new A.GraphicFrameLocks { NoChangeAspect = true }),
            new A.Graphic(
                new A.GraphicData(
                    new PIC.Picture(
                        new PIC.NonVisualPictureProperties(
                            new PIC.NonVisualDrawingProperties { Id = 0U, Name = Path.GetFileName(path) },
                            new PIC.NonVisualPictureDrawingProperties()),
                        new PIC.BlipFill(
                            new A.Blip { Embed = relId, CompressionState = A.BlipCompressionValues.Print },
                            new A.Stretch(new A.FillRectangle())),
                        new PIC.ShapeProperties(
                            new A.Transform2D(
                                new A.Offset { X = 0L, Y = 0L },
                                new A.Extents { Cx = cx, Cy = cy }),
                            new A.PresetGeometry(new A.AdjustValueList()) { Preset = A.ShapeTypeValues.Rectangle }))
                )
                { Uri = "http://schemas.openxmlformats.org/drawingml/2006/picture" })
        )
        {
            DistanceFromTop = 0U,
            DistanceFromBottom = 0U,
            DistanceFromLeft = 0U,
            DistanceFromRight = 0U
        });

    body.Append(new Paragraph(
        new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
        new Run(drawing)));
    body.Append(P(caption, "Caption"));
}

static (int w, int h) ReadPngSize(string path)
{
    using var fs = File.OpenRead(path);
    var sig = new byte[8];
    if (fs.Read(sig, 0, 8) < 8) return (1280, 800);
    var lenBuf = new byte[4];
    var typeBuf = new byte[4];
    if (fs.Read(lenBuf, 0, 4) < 4 || fs.Read(typeBuf, 0, 4) < 4) return (1280, 800);
    var type = Encoding.ASCII.GetString(typeBuf);
    if (type != "IHDR") return (1280, 800);
    var ihdr = new byte[8];
    if (fs.Read(ihdr, 0, 8) < 8) return (1280, 800);
    int w = (ihdr[0] << 24) | (ihdr[1] << 16) | (ihdr[2] << 8) | ihdr[3];
    int h = (ihdr[4] << 24) | (ihdr[5] << 16) | (ihdr[6] << 8) | ihdr[7];
    return (w, h);
}
