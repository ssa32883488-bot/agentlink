using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using A = DocumentFormat.OpenXml.Drawing;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;

var Root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
var Dir = "chat_dual_20261030_110903";
var OutPath = Path.Combine(Root, $"AgentLink_对话双路径验证报告_{DateTime.Now:yyyyMMdd_HHmm}.docx");
uint DocPropId = 1;

string Shot(string name) => Path.Combine(Root, Dir, "screenshots", name);

using var doc = WordprocessingDocument.Create(OutPath, WordprocessingDocumentType.Document);
var main = doc.AddMainDocumentPart();
main.Document = new Document(new Body());
var body = main.Document.Body!;
var stylesPart = main.AddNewPart<StyleDefinitionsPart>();
stylesPart.Styles = BuildStyles();

void H1(string t) => body.Append(P(t, "Heading1"));
void H2(string t) => body.Append(P(t, "Heading2"));
void H3(string t) => body.Append(P(t, "Heading3"));
void Para(string t) => body.Append(P(t, "Normal"));
void Bullet(string t) => body.Append(P("• " + t, "Normal"));

Paragraph P(string text, string style)
{
    return new Paragraph(
        new ParagraphProperties(new ParagraphStyleId { Val = style }),
        new Run(new RunProperties(new RunFonts { Ascii = "Calibri", HighAnsi = "Calibri", EastAsia = "微软雅黑" }), new Text(text) { Space = SpaceProcessingModeValues.Preserve })
    );
}

void Cap(string t)
{
    body.Append(new Paragraph(
        new ParagraphProperties(
            new ParagraphStyleId { Val = "Normal" },
            new Justification { Val = JustificationValues.Center }
        ),
        new Run(
            new RunProperties(
                new RunFonts { Ascii = "Calibri", HighAnsi = "Calibri", EastAsia = "微软雅黑" },
                new Italic(),
                new FontSize { Val = "18" },
                new Color { Val = "666666" }
            ),
            new Text(t) { Space = SpaceProcessingModeValues.Preserve }
        )
    ));
}

(int w, int h) ReadPngSize(string path)
{
    using var br = new BinaryReader(File.OpenRead(path));
    br.ReadBytes(16);
    int w = (br.ReadByte() << 24) | (br.ReadByte() << 16) | (br.ReadByte() << 8) | br.ReadByte();
    int h = (br.ReadByte() << 24) | (br.ReadByte() << 16) | (br.ReadByte() << 8) | br.ReadByte();
    return (w, h);
}

void AddImage(string path, string caption, int widthPx = 520)
{
    if (!File.Exists(path))
    {
        Para($"（缺图：{Path.GetFileName(path)}）");
        return;
    }
    var (iw, ih) = ReadPngSize(path);
    int h = Math.Max(1, (int)(widthPx * (double)ih / Math.Max(1, iw)));

    var part = main.AddImagePart(ImagePartType.Png);
    using (var fs = File.OpenRead(path)) part.FeedData(fs);
    string relId = main.GetIdOfPart(part);
    long cx = widthPx * 9525L;
    long cy = h * 9525L;
    uint id = DocPropId++;

    var drawing = new Drawing(
        new DW.Inline(
            new DW.Extent { Cx = cx, Cy = cy },
            new DW.EffectExtent { LeftEdge = 0L, TopEdge = 0L, RightEdge = 0L, BottomEdge = 0L },
            new DW.DocProperties { Id = id, Name = $"Picture {id}" },
            new DW.NonVisualGraphicFrameDrawingProperties(new A.GraphicFrameLocks { NoChangeAspect = true }),
            new A.Graphic(
                new A.GraphicData(
                    new PIC.Picture(
                        new PIC.NonVisualPictureProperties(
                            new PIC.NonVisualDrawingProperties { Id = 0U, Name = Path.GetFileName(path) },
                            new PIC.NonVisualPictureDrawingProperties()
                        ),
                        new PIC.BlipFill(
                            new A.Blip { Embed = relId },
                            new A.Stretch(new A.FillRectangle())
                        ),
                        new PIC.ShapeProperties(
                            new A.Transform2D(
                                new A.Offset { X = 0L, Y = 0L },
                                new A.Extents { Cx = cx, Cy = cy }
                            ),
                            new A.PresetGeometry(new A.AdjustValueList()) { Preset = A.ShapeTypeValues.Rectangle }
                        )
                    )
                )
                { Uri = "http://schemas.openxmlformats.org/drawingml/2006/picture" }
            )
        )
    );

    body.Append(new Paragraph(new Run(drawing)));
    Cap(caption);
}

void AddTable(string[] headers, string[][] rows)
{
    var table = new Table(
        new TableProperties(
            new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct },
            new TableBorders(
                new TopBorder { Val = BorderValues.Single, Size = 4 },
                new BottomBorder { Val = BorderValues.Single, Size = 4 },
                new LeftBorder { Val = BorderValues.Single, Size = 4 },
                new RightBorder { Val = BorderValues.Single, Size = 4 },
                new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4 },
                new InsideVerticalBorder { Val = BorderValues.Single, Size = 4 }
            )
        )
    );
    var hdr = new TableRow();
    foreach (var h in headers)
    {
        hdr.Append(new TableCell(
            new TableCellProperties(new Shading { Val = ShadingPatternValues.Clear, Fill = "1F3864" }),
            new Paragraph(new Run(new RunProperties(new RunFonts { EastAsia = "微软雅黑" }, new Bold(), new Color { Val = "FFFFFF" }, new FontSize { Val = "18" }), new Text(h)))
        ));
    }
    table.Append(hdr);
    bool alt = false;
    foreach (var row in rows)
    {
        var tr = new TableRow();
        foreach (var cell in row)
        {
            var props = new TableCellProperties();
            if (alt) props.Append(new Shading { Val = ShadingPatternValues.Clear, Fill = "F5F7FA" });
            tr.Append(new TableCell(props, new Paragraph(new Run(new RunProperties(new RunFonts { EastAsia = "微软雅黑" }, new FontSize { Val = "18" }), new Text(cell)))));
        }
        table.Append(tr);
        alt = !alt;
    }
    body.Append(table);
    body.Append(new Paragraph());
}

Styles BuildStyles()
{
    var styles = new Styles(
        new DocDefaults(
            new RunPropertiesDefault(new RunPropertiesBaseStyle(
                new RunFonts { Ascii = "Calibri", HighAnsi = "Calibri", EastAsia = "微软雅黑" },
                new FontSize { Val = "22" }
            )),
            new ParagraphPropertiesDefault(new ParagraphProperties(
                new SpacingBetweenLines { After = "120", Line = "276", LineRule = LineSpacingRuleValues.Auto }
            ))
        )
    );
    styles.Append(MakeStyle("Normal", "Normal", "段落", false, "22", "333333"));
    styles.Append(MakeStyle("Heading1", "Heading1", "标题 1", true, "36", "1F3864", based: "Normal"));
    styles.Append(MakeStyle("Heading2", "Heading2", "标题 2", true, "28", "2E5090", based: "Normal"));
    styles.Append(MakeStyle("Heading3", "Heading3", "标题 3", true, "24", "404040", based: "Normal"));
    return styles;
}

Style MakeStyle(string id, string name, string nameZh, bool bold, string sz, string color, string? based = null)
{
    var s = new Style { Type = StyleValues.Paragraph, StyleId = id };
    s.Append(new StyleName { Val = name });
    if (based != null) s.Append(new BasedOn { Val = based });
    var rPr = new StyleRunProperties(new RunFonts { Ascii = "Calibri", HighAnsi = "Calibri", EastAsia = "微软雅黑" }, new FontSize { Val = sz }, new Color { Val = color });
    if (bold) rPr.Append(new Bold());
    s.Append(rPr);
    s.Append(new StyleParagraphProperties(new SpacingBetweenLines { Before = id.StartsWith("Heading") ? "240" : "60", After = "120" }));
    return s;
}

const string Q1 = "我打算购买 500 套重型脚轮300kg，请发现供应商并报价。先给出候选，再统一询价；我确认后再下单。";
const string Q2 = "单物料复杂采购：标准脚轮200kg、数量500（多家目录都有）。请发现多家供应商后统一询价；若多家都能供且可比，请走组群竞价+TCO，再选最优方案下单。";

H1("AgentLink 对话驱动双路径验证报告");
Para($"生成时间：{DateTime.Now:yyyy-MM-dd HH:mm}");
Para($"证据目录：{Dir}（浏览器提问入口 + 全过程截图共 27 张）");
Para("本报告按「两条具体采购话术」各跑一边：先在采购对话里真实提问，再记录短名单/选项、工单、供应确认、物流与终态。");

H2("一、两条具体问题");
Bullet($"普通询价：{Q1}");
Bullet($"组群竞价：{Q2}");

H2("二、结论总览");
AddTable(
    new[] { "路径", "结果", "案号", "说明" },
    new[]
    {
        new[] { "普通询价", "PASS", "case-49fd43fa → ACTIVE", "对话提问 → 发现 3 家 → 下单 A @18×500=9000" },
        new[] { "组群竞价", "PASS", "case-5f036b22 → ACTIVE", "对话提问 → 出价 2 家；transport=rpc 回退；下单 A 货款 6750" },
    }
);

H2("三、普通询价（问题一）");
H3("3.1 入口话术与结果");
Para($"提问：{Q1}");
Bullet("发现：platform_adp，候选 A/B/C");
Bullet("下单 supplier-a，重型脚轮300kg ×500，单价 18，货款 9000 → ACTIVE");

H3("3.2 全过程截图");
AddImage(Shot("01_N00_empty_chat.png"), "图1 新对话空线程");
AddImage(Shot("02_N01_ask_normal_rfq.png"), "图2 提出普通询价问题后的助手回复");
AddImage(Shot("03_N02_shortlist_try.png"), "图3 短名单交互尝试");
AddImage(Shot("04_N03_choice_try.png"), "图4 选项交互尝试");
AddImage(Shot("05_N04_chat_status_after_core.png"), "图5 推进后对话状态汇总");
AddImage(Shot("06_N05_buyer_tickets.png"), "图6 采购工单");
AddImage(Shot("07_N06_sa_tickets.png"), "图7 供应 A 工单");
AddImage(Shot("10_N07_sa_after_ack.png"), "图8 供应确认后");
AddImage(Shot("11_N08_logistics.png"), "图9 物流端");
AddImage(Shot("12_N09_final_tickets.png"), "图10 终态工单");
AddImage(Shot("13_N10_audit.png"), "图11 审计");
AddImage(Shot("14_N11_chat_final.png"), "图12 终态确认对话");

H2("四、组群竞价（问题二）");
H3("4.1 入口话术与结果");
Para($"提问：{Q2}");
Bullet("RFQ 2 家报价 → auction；有效出价 A/C；本轮 group invite 失败后 RPC 盲标回退");
Bullet("下单 supplier-a，标准脚轮200kg ×500，货款 6750 → ACTIVE");

H3("4.2 全过程截图");
AddImage(Shot("15_A00_empty_chat.png"), "图13 新对话空线程");
AddImage(Shot("16_A01_ask_group_auction.png"), "图14 提出组群竞价问题后的助手回复");
AddImage(Shot("17_A02_shortlist_try.png"), "图15 短名单交互");
AddImage(Shot("18_A03_choice_auction.png"), "图16 竞价相关选项交互");
AddImage(Shot("19_A04_chat_auction_summary.png"), "图17 竞价结果对话汇总");
AddImage(Shot("20_A05_buyer_tickets.png"), "图18 采购工单");
AddImage(Shot("21_A06_sa_tickets.png"), "图19 供应 A");
AddImage(Shot("23_A07_sa_after_ack.png"), "图20 供应确认后");
AddImage(Shot("24_A08_logistics.png"), "图21 物流端");
AddImage(Shot("25_A09_final_tickets.png"), "图22 终态工单");
AddImage(Shot("26_A10_audit.png"), "图23 审计");
AddImage(Shot("27_A11_chat_final.png"), "图24 终态确认对话");

H2("五、证据位置");
Para($"Markdown：docs/evidence/verify_ui_shots/{Dir}/REVIEW.md");
Bullet($"全部 27 张 PNG：{Dir}/screenshots/");
Bullet("业务日志：normal_*.log / auction_*.log");

body.Append(new SectionProperties(
    new PageSize { Width = 11906, Height = 16838 },
    new PageMargin { Top = 1134, Bottom = 1134, Left = 1134, Right = 1134, Header = 720, Footer = 720 }
));

main.Document.Save();
Console.WriteLine("WROTE " + OutPath);
