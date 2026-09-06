{==============================================================================
  伊利雪糕三棒签同步插签设备 —— PLC控制原理图自动生成脚本
  适用软件：Altium Designer 18+
  运行方式：DXP -> Run Script -> 选择本文件 -> 执行 GenerateStickInsertSchematic
  功能：自动生成包含 PLC、三路气缸电磁阀、位置传感器、急停、电源、端子排
        的完整控制原理图，并标注差异化延时同步控制逻辑。
==============================================================================}
Var
    CurrentSheet : ISch_Document;
    X, Y : Integer;

{ 在当前原理图放置一个元件（通过库引用）}
Procedure PlaceComponent(RefDes, Comment, LibName, CompName : String; Xpos, Ypos : Integer);
Var
    Comp : ISch_Component;
Begin
    Comp := SchServer.SchObjectFactory(eSchComponent, eCreate_Default);
    If Comp = Nil Then Exit;
    Comp.Location := Point(Xpos, Ypos);
    Comp.Designator.Text := RefDes;
    Comp.Comment.Text := Comment;
    Comp.LibName := LibName;
    Comp.SourceLibName := LibName;
    Comp.LibReference := CompName;
    CurrentSheet.AddSchObject(Comp);
End;

{ 放置网络标签 }
Procedure PlaceNetLabel(NetName : String; Xpos, Ypos : Integer);
Var
    NL : ISch_NetLabel;
Begin
    NL := SchServer.SchObjectFactory(eSchNetLabel, eCreate_Default);
    If NL = Nil Then Exit;
    NL.Location := Point(Xpos, Ypos);
    NL.Text := NetName;
    CurrentSheet.AddSchObject(NL);
End;

{ 放置导线 }
Procedure PlaceWire(X1, Y1, X2, Y2 : Integer);
Var
    Wire : ISch_Wire;
Begin
    Wire := SchServer.SchObjectFactory(eSchWire, eCreate_Default);
    If Wire = Nil Then Exit;
    Wire.Location := Point(X1, Y1);
    Wire.Corner := Point(X2, Y2);
    CurrentSheet.AddSchObject(Wire);
End;

{ 放置文字标注 }
Procedure PlaceNote(Text : String; Xpos, Ypos : Integer; FontSize : Integer);
Var
    Note : ISch_Text;
Begin
    Note := SchServer.SchObjectFactory(eSchText, eCreate_Default);
    If Note = Nil Then Exit;
    Note.Location := Point(Xpos, Ypos);
    Note.Text := Text;
    Note.Font.Size := FontSize;
    CurrentSheet.AddSchObject(Note);
End;

{ 主函数：生成PLC控制原理图 }
Procedure GenerateStickInsertSchematic;
Var
    Sheet : ISch_Document;
Begin
    { 创建新原理图文档 }
    Sheet := SchServer.SchObjectFactory(eSchDocument, eCreate_Default);
    If Sheet = Nil Then
    Begin
        ShowMessage('无法创建原理图文档，请确认已打开一个PCB工程');
        Exit;
    End;
    CurrentSheet := Sheet;
    Sheet.DocumentName := 'StickInsert_Control.SchDoc';

    { ===== 标题栏 ===== }
    PlaceNote('伊利雪糕三棒签同步插签设备 —— PLC控制原理图', 100, 20, 16);
    PlaceNote('设计：陈坤  日期：2026-08  版本：V1.0', 100, 50, 10);
    PlaceNote('控制逻辑：三气缸差异化延时补偿 + 同步收尾 + 过载保护 + 偏差自检', 100, 70, 10);

    { ===== 电源部分 ===== }
    PlaceNote('=== 电源 ===', 50, 120, 12);
    PlaceComponent('P1', 'DC24V电源', 'Miscellaneous Devices.IntLib', 'DC24V', 100, 180);
    PlaceNetLabel('+24V', 130, 160);
    PlaceNetLabel('GND', 130, 220);

    { ===== PLC 主控 ===== }
    PlaceNote('=== PLC 主控（西门子S7-1200 / 兼容三菱FX系列）===', 300, 120, 12);
    PlaceComponent('U1', 'PLC CPU 1214C', 'PLC.IntLib', 'CPU1214C', 400, 250);
    PlaceNote('DI: 急停/传感器    DO: 三路电磁阀输出    AI: 负载电流检测', 350, 400, 9);

    { ===== 三路气缸电磁阀输出 ===== }
    PlaceNote('=== 三路气缸电磁阀（差异化延时控制）===', 700, 120, 12);

    { 气缸1 - 短行程棒签 }
    PlaceComponent('YV1', '电磁阀1 (短缸30mm)', 'Miscellaneous Devices.IntLib', 'Relay-SPST', 750, 200);
    PlaceNetLabel('PLC_Q0.0', 720, 200);
    PlaceNote('延时250ms启动', 750, 240, 9);

    { 气缸2 - 中行程棒签 }
    PlaceComponent('YV2', '电磁阀2 (中缸45mm)', 'Miscellaneous Devices.IntLib', 'Relay-SPST', 750, 320);
    PlaceNetLabel('PLC_Q0.1', 720, 320);
    PlaceNote('延时125ms启动', 750, 360, 9);

    { 气缸3 - 长行程棒签 }
    PlaceComponent('YV3', '电磁阀3 (长缸60mm)', 'Miscellaneous Devices.IntLib', 'Relay-SPST', 750, 440);
    PlaceNetLabel('PLC_Q0.2', 720, 440);
    PlaceNote('立即启动(基准)', 750, 480, 9);

    { ===== 位置传感器反馈 ===== }
    PlaceNote('=== 位置传感器（到位反馈）===', 50, 550, 12);
    PlaceComponent('SQ1', '气缸1到位传感器', 'Miscellaneous Devices.IntLib', 'SW-PB', 100, 620);
    PlaceComponent('SQ2', '气缸2到位传感器', 'Miscellaneous Devices.IntLib', 'SW-PB', 100, 680);
    PlaceComponent('SQ3', '气缸3到位传感器', 'Miscellaneous Devices.IntLib', 'SW-PB', 100, 740);
    PlaceNetLabel('PLC_I0.0', 150, 620);
    PlaceNetLabel('PLC_I0.1', 150, 680);
    PlaceNetLabel('PLC_I0.2', 150, 740);

    { ===== 急停与过载保护 ===== }
    PlaceNote('=== 急停 / 过载保护 ===', 400, 550, 12);
    PlaceComponent('SB1', '急停按钮(常闭)', 'Miscellaneous Devices.IntLib', 'SW-PB', 450, 620);
    PlaceNetLabel('PLC_I0.3', 500, 620);
    PlaceComponent('FR1', '过载保护继电器', 'Miscellaneous Devices.IntLib', 'Fuse', 450, 700);
    PlaceNetLabel('PLC_I0.4', 500, 700);

    { ===== 端子排 ===== }
    PlaceNote('=== 外部端子排 ===', 700, 550, 12);
    PlaceComponent('XT1', '端子排 8P', 'Miscellaneous Connectors.IntLib', 'Header 8', 750, 650);

    { ===== 控制逻辑说明 ===== }
    PlaceNote('=== PLC控制逻辑说明 ===', 50, 820, 12);
    PlaceNote('1. 启动信号 -> 气缸3立即启动，气缸2延时125ms，气缸1延时250ms', 50, 850, 10);
    PlaceNote('2. 三缸梯形速度曲线运动，同时到达插入位（理论到位时间差=0ms）', 50, 875, 10);
    PlaceNote('3. 到位传感器SQ1~SQ3反馈 -> PLC判定同步性，偏差>1.5mm触发闭环补偿', 50, 900, 10);
    PlaceNote('4. 急停SB1 / 过载FR1 -> 立即切断所有电磁阀输出', 50, 925, 10);
    PlaceNote('5. 控制周期10ms，对应PLC扫描周期；上位机通过Qt界面监控与参数调整', 50, 950, 10);

    { 刷新原理图 }
    CurrentSheet.Modified := True;
    Client.OpenDocument('SCH', CurrentSheet.DocumentName);
    ShowMessage('PLC控制原理图已生成！请检查元件库引用并编译工程。');
End;
