using System.Drawing;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using A = DocumentFormat.OpenXml.Drawing;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;

static string FindEvidenceRoot()
{
    var candidates = new[]
    {
        Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "docs", "evidence", "verify_ui_shots", "v2_dual_20261030_194944")),
        Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", "..", "..", "docs", "evidence", "verify_ui_shots", "v2_dual_20261030_194944")),
        @"f:\code\智能体协议\项目开发\agentlink\docs\evidence\verify_ui_shots\v2_dual_20261030_194944",
    };
    foreach (var c in candidates)
    {
        if (File.Exists(Path.Combine(c, "report.json"))) return c;
    }
    throw new DirectoryNotFoundException("evidence folder not found");
}

var root = FindEvidenceRoot();
var reportPath = Path.Combine(root, "report.json");
using var reportDoc = JsonDocument.Parse(File.ReadAllText(reportPath, Encoding.UTF8));
var report = reportDoc.RootElement;
var runId = report.GetProperty("run_id").GetString() ?? "run";
var url = report.GetProperty("url").GetString() ?? "";
var demand = report.GetProperty("demand").GetString() ?? "";
var notes = report.GetProperty("notes");
var steps = report.GetProperty("steps").EnumerateArray().ToList();

var outDir = root;
var outPath = Path.Combine(outDir, $"commerce_v2_双路径询价全流程_{runId}.docx");

uint docPropId = 1;

using (var word = WordprocessingDocument.Create(outPath, WordprocessingDocumentType.Document))
{
    var main = word.AddMainDocumentPart();
    main.Document = new Document();
    var body = main.Document.AppendChild(new Body());

    EnsureStyles(main);

    AddHeading(body, "AgentLink commerce_v2 双路径询价全流程截图报告", 1);
    AddPara(body, $"运行编号：{runId}");
    AddPara(body, $"界面入口：{url}");
    AddPara(body, $"统一需求话术：{demand}");
    AddPara(body, $"生成时间：{DateTime.Now:yyyy-MM-dd HH:mm}");
    AddPara(body, "");

    AddHeading(body, "一、路径说明", 1);
    AddPara(body, "1. 普通询价：需求改写与发现 → 短名单确认并询价 → 初报/议价询问。");
    AddPara(body, "2. 组群竞价：需求改写与发现 →「我要组群竞价」→ 勾选供应+物流入群 → 组群聊天室按行报价 → 全量覆盖方案选择。");
    AddPara(body, "");

    AddHeading(body, "二、运行结果摘要", 1);
    AddPara(body, $"普通询价：{notes.GetProperty("normal").GetProperty("flow").GetString()}");
    AddPara(body, $"  · shortlist_clicked = {notes.GetProperty("normal").GetProperty("shortlist_clicked")}");
    AddPara(body, $"组群竞价：{notes.GetProperty("group").GetProperty("flow").GetString()}");
    AddPara(body, $"  · group_confirm={notes.GetProperty("group").GetProperty("group_confirm_clicked")} · room_opened={notes.GetProperty("group").GetProperty("room_opened")} · plan_clicked={notes.GetProperty("group").GetProperty("plan_clicked")}");
    AddPara(body, "");

    AddHeading(body, "三、逐步截图与处理日志", 1);

    bool normalHeading = false, groupHeading = false;
    foreach (var step in steps)
    {
        var label = step.GetProperty("label").GetString() ?? "";
        var file = step.GetProperty("file").GetString() ?? "";
        var note = step.TryGetProperty("note", out var n) ? n.GetString() ?? "" : "";
        var chat = step.TryGetProperty("chat", out var c) ? c.GetString() ?? "" : "";
        var flow = step.TryGetProperty("flow", out var f) ? f.GetString() ?? "" : "";
        var stepNo = step.GetProperty("step").GetInt32();
        var logMdRel = step.TryGetProperty("log_md", out var lm) ? lm.GetString() ?? "" : "";

        if (label.StartsWith("N") && !normalHeading)
        {
            AddHeading(body, "3.1 路径 A · 普通询价", 2);
            normalHeading = true;
        }
        if (label.StartsWith("G") && !groupHeading)
        {
            AddHeading(body, "3.2 路径 B · 组群竞价", 2);
            groupHeading = true;
        }

        AddHeading(body, $"{stepNo:00}. {label}", 3);
        if (!string.IsNullOrWhiteSpace(chat))
            AddPara(body, $"输入：{chat}", boldLabel: "输入");
        if (!string.IsNullOrWhiteSpace(note))
            AddPara(body, $"说明：{note}");
        if (!string.IsNullOrWhiteSpace(flow))
            AddPara(body, $"案状态：{flow}");

        var imgPath = Path.Combine(root, "screenshots", file);
        if (File.Exists(imgPath))
        {
            AddPara(body, "界面截图：");
            InsertScaledImage(main, body, imgPath, maxWidthInches: 6.3, ref docPropId);
        }
        else
        {
            AddPara(body, $"（截图缺失：{file}）");
        }

        var logPath = string.IsNullOrEmpty(logMdRel) ? "" : Path.Combine(root, logMdRel.Replace('/', Path.DirectorySeparatorChar));
        if (File.Exists(logPath))
        {
            var logText = ExtractTrailSummary(File.ReadAllText(logPath, Encoding.UTF8));
            if (!string.IsNullOrWhiteSpace(logText))
            {
                AddPara(body, "处理轨迹 / 关键日志：");
                AddCodeBlock(body, logText);
            }
        }

        AddPara(body, "");
    }

    AddHeading(body, "四、附录", 1);
    AddPara(body, $"证据目录：{root}");
    AddPara(body, "原始文件：REVIEW.md、report.json、screenshots/、logs/");

    // section properties last
    body.AppendChild(new SectionProperties(
        new PageSize { Width = 11906, Height = 16838 }, // A4
        new PageMargin
        {
            Top = 1134,
            Bottom = 1134,
            Left = 1134,
            Right = 1134,
            Header = 720,
            Footer = 720
        }
    ));

    main.Document.Save();
}

Console.WriteLine("DOCX_OK " + outPath);

static void EnsureStyles(MainDocumentPart main)
{
    var stylesPart = main.StyleDefinitionsPart ?? main.AddNewPart<StyleDefinitionsPart>();
    stylesPart.Styles ??= new Styles();
    var styles = stylesPart.Styles;

    void AddHeadingStyle(string id, string name, int outline, string size)
    {
        if (styles.Elements<Style>().Any(s => s.StyleId == id)) return;
        styles.AppendChild(new Style(
            new StyleName { Val = name },
            new BasedOn { Val = "Normal" },
            new UIPriority { Val = 9 },
            new PrimaryStyle(),
            new StyleParagraphProperties(
                new OutlineLevel { Val = outline },
                new SpacingBetweenLines { Before = "240", After = "120" },
                new KeepNext()
            ),
            new StyleRunProperties(
                new Bold(),
                new RunFonts { Ascii = "Microsoft YaHei", HighAnsi = "Microsoft YaHei", EastAsia = "Microsoft YaHei" },
                new FontSize { Val = size },
                new FontSizeComplexScript { Val = size }
            )
        )
        { Type = StyleValues.Paragraph, StyleId = id });
    }

    if (!styles.Elements<Style>().Any(s => s.StyleId == "Normal"))
    {
        styles.AppendChild(new Style(
            new StyleName { Val = "Normal" },
            new PrimaryStyle(),
            new StyleParagraphProperties(
                new SpacingBetweenLines { After = "80", Line = "360", LineRule = LineSpacingRuleValues.Auto }
            ),
            new StyleRunProperties(
                new RunFonts { Ascii = "Microsoft YaHei", HighAnsi = "Microsoft YaHei", EastAsia = "Microsoft YaHei" },
                new FontSize { Val = "21" },
                new FontSizeComplexScript { Val = "21" }
            )
        )
        { Type = StyleValues.Paragraph, StyleId = "Normal", Default = true });
    }

    AddHeadingStyle("Heading1", "heading 1", 0, "32");
    AddHeadingStyle("Heading2", "heading 2", 1, "28");
    AddHeadingStyle("Heading3", "heading 3", 2, "24");
}

static void AddHeading(Body body, string text, int level)
{
    var style = level switch { 1 => "Heading1", 2 => "Heading2", _ => "Heading3" };
    body.AppendChild(new Paragraph(
        new ParagraphProperties(new ParagraphStyleId { Val = style }),
        new Run(new Text(text) { Space = SpaceProcessingModeValues.Preserve })
    ));
}

static void AddPara(Body body, string text, string? boldLabel = null)
{
    var p = new Paragraph();
    p.AppendChild(new ParagraphProperties(
        new SpacingBetweenLines { After = "60" }
    ));
    p.AppendChild(new Run(
        new RunProperties(
            new RunFonts { Ascii = "Microsoft YaHei", HighAnsi = "Microsoft YaHei", EastAsia = "Microsoft YaHei" },
            new FontSize { Val = "21" }
        ),
        new Text(text ?? "") { Space = SpaceProcessingModeValues.Preserve }
    ));
    body.AppendChild(p);
}

static void AddCodeBlock(Body body, string text)
{
    var lines = text.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
    foreach (var line in lines.Take(80))
    {
        body.AppendChild(new Paragraph(
            new ParagraphProperties(
                new SpacingBetweenLines { After = "0", Before = "0", Line = "276", LineRule = LineSpacingRuleValues.Auto },
                new Shading { Val = ShadingPatternValues.Clear, Fill = "F3F4F6" }
            ),
            new Run(
                new RunProperties(
                    new RunFonts { Ascii = "Consolas", HighAnsi = "Consolas", EastAsia = "Microsoft YaHei" },
                    new FontSize { Val = "16" },
                    new FontSizeComplexScript { Val = "16" }
                ),
                new Text(line.Length == 0 ? " " : line) { Space = SpaceProcessingModeValues.Preserve }
            )
        ));
    }
    if (lines.Length > 80)
    {
        AddPara(body, $"……（已截断，完整日志见 logs/ 目录，共 {lines.Length} 行）");
    }
}

static string ExtractTrailSummary(string md)
{
    var sb = new StringBuilder();
    var lines = md.Replace("\r\n", "\n").Split('\n');
    bool inTrail = false;
    int trailBlocks = 0;
    foreach (var raw in lines)
    {
        var line = raw.TrimEnd();
        if (line.StartsWith("- flow:") || line.StartsWith("- roomOpen:") || line.StartsWith("- room:"))
        {
            sb.AppendLine(line.TrimStart('-', ' '));
            continue;
        }
        if (line.StartsWith("## 处理轨迹") || line.StartsWith("## 组群聊天室") || line.StartsWith("## 短名单") || line.StartsWith("## 决策"))
        {
            inTrail = true;
            trailBlocks++;
            if (trailBlocks > 3) break;
            sb.AppendLine(line.TrimStart('#', ' '));
            continue;
        }
        if (line.StartsWith("### 回复摘录"))
        {
            inTrail = false;
            continue;
        }
        if (line.StartsWith("```"))
        {
            inTrail = !inTrail && false;
            continue;
        }
        if (inTrail && line.StartsWith("- "))
        {
            sb.AppendLine(line[2..]);
        }
        else if (inTrail && line.Length > 0 && !line.StartsWith("#"))
        {
            // keep short room excerpts
            if (sb.Length < 3500)
                sb.AppendLine(line);
        }
    }
    var s = sb.ToString().Trim();
    if (s.Length > 4500) s = s[..4500] + "\n……";
    return s;
}

static void InsertScaledImage(MainDocumentPart main, Body body, string imagePath, double maxWidthInches, ref uint docPropId)
{
    int pxW, pxH;
    using (var img = Image.FromFile(imagePath))
    {
        pxW = img.Width;
        pxH = img.Height;
    }

    const long emuPerInch = 914400L;
    const long emuPerPx = 9525L;
    long maxCx = (long)(maxWidthInches * emuPerInch);
    long cx = pxW * emuPerPx;
    long cy = pxH * emuPerPx;
    if (cx > maxCx)
    {
        double scale = (double)maxCx / cx;
        cx = maxCx;
        cy = (long)(cy * scale);
    }

    var imagePart = main.AddImagePart(ImagePartType.Png);
    using (var fs = File.OpenRead(imagePath))
        imagePart.FeedData(fs);
    string relId = main.GetIdOfPart(imagePart);
    uint id = docPropId++;

    var drawing = new Drawing(
        new DW.Inline(
            new DW.Extent { Cx = cx, Cy = cy },
            new DW.EffectExtent { LeftEdge = 0L, TopEdge = 0L, RightEdge = 0L, BottomEdge = 0L },
            new DW.DocProperties { Id = id, Name = $"Shot{id}" },
            new DW.NonVisualGraphicFrameDrawingProperties(
                new A.GraphicFrameLocks { NoChangeAspect = true }),
            new A.Graphic(
                new A.GraphicData(
                    new PIC.Picture(
                        new PIC.NonVisualPictureProperties(
                            new PIC.NonVisualDrawingProperties { Id = 0U, Name = Path.GetFileName(imagePath) },
                            new PIC.NonVisualPictureDrawingProperties()),
                        new PIC.BlipFill(
                            new A.Blip { Embed = relId },
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

    body.AppendChild(new Paragraph(new Run(drawing)));
}
