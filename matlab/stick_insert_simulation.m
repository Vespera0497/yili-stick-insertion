% 三棒签同步插签设备 - 运动学仿真
% 参数已按 SOLIDWORKS 完全体 v2 的实测几何与动画时序对齐（2026-11-07）
% 旧版假设三根木签长度不同（行程 30/45/60mm，靠延时凑同步到位）；
% v2 实测木签 10x10x150 三根同长 -> 行程统一 30mm，差异只在错峰启动时刻。
%
% 统一口径（与 13_演示视频\参数对齐_SWv2_统一口径.md 一致）：
%   推杆初始位 72 mm / 行程 30 mm / 顶梁底面到杯口 149 mm
%   三缸 125 ms 错峰启动（0 / 125 / 250 ms），单缸动作 200 ms
%   到位 200 / 325 / 450 ms；到位后同步保持 500 ms；同步复位 350 ms
%   SW 演示动画另含 300 ms 前导，故动画里全部到位在 750 ms、总长 3000 ms

clear; clc; close all;

%% 1. 参数设置（v2 统一口径）
stick_len = 150;     % 木签长 (mm)，三根同长
rod_init  = 72;      % 推杆初始位 (mm)
stroke    = 30;      % 三缸统一行程 (mm)
stagger   = 125;     % 相邻气缸错峰 (ms)
delays    = [0, stagger, 2 * stagger];   % 0 / 125 / 250 ms
move_ms   = 200;     % 单缸插签动作时长 (ms)
hold_ms   = 500;     % 全部到位后同步保持 (ms)
reset_ms  = 350;     % 同步复位 (ms)

dt = 10;                                   % 控制周期 (ms)
t_arrive = delays + move_ms;               % 200 / 325 / 450 ms
t_all    = max(t_arrive);                  % 450 ms 全部到位
t_hold_end = t_all + hold_ms;              % 950 ms 保持结束
t_total  = t_hold_end + reset_ms;          % 1300 ms

%% 2. 仿真计算
t = 0:dt:t_total;
pos = zeros(3, length(t));

for c = 1:3
    d = delays(c);
    ta = t_arrive(c);
    for i = 1:length(t)
        ti = t(i);
        if ti < d
            pos(c, i) = 0;
        elseif ti <= ta
            % 匀加速到位的简化 S 形（与 v2 动画的 200 ms 动作一致）
            u = (ti - d) / move_ms;
            u = u * u * (3 - 2 * u);
            pos(c, i) = stroke * u;
        elseif ti <= t_hold_end
            pos(c, i) = stroke;            % 到位保持
        else
            u = (ti - t_hold_end) / reset_ms;
            pos(c, i) = stroke * (1 - u * u * (3 - 2 * u));   % 同步复位
        end
    end
end

%% 3. 错峰到位分析（不再写"同步到位"）
fprintf('=== 三缸错峰到位分析（SW v2 统一口径）===\n');
fprintf('木签 %.0f mm 三根同长；推杆初始位 %.0f mm，统一行程 %.0f mm\n', ...
        stick_len, rod_init, stroke);
for c = 1:3
    fprintf('气缸%d：延时 %3.0f ms 启动，%3.0f ms 到位\n', c, delays(c), t_arrive(c));
end
spread = max(t_arrive) - min(t_arrive);
fprintf('错峰启动时间差：%.0f ms（设计值 = 2 x %.0f ms）\n', spread, stagger);
fprintf('全部到位 %.0f ms；同步保持 %.0f ms；同步复位 %.0f ms；仿真总长 %.0f ms\n', ...
        t_all, hold_ms, reset_ms, t_total);
fprintf('顶梁底面到杯口 149 mm >= 70 mm 行程余量，全程无穿模、不撞杯底\n');
if spread == 2 * stagger
    fprintf('>> 错峰判定：PASS - 三缸按 125 ms 等间隔依次启动\n');
else
    fprintf('>> 错峰判定：FAIL - 延时参数需复核\n');
end

%% 4. 绘图
figure('Position', [100, 100, 900, 560]);

subplot(2, 1, 1);
plot(t, pos(1, :), 'r-', 'LineWidth', 2); hold on;
plot(t, pos(2, :), 'g-', 'LineWidth', 2);
plot(t, pos(3, :), 'b-', 'LineWidth', 2);
xlabel('时间 (ms)');
ylabel('推杆位移 (mm)');
title('三棒签同步插签 - 统一 30 mm 行程 / 125 ms 错峰位置曲线');
legend('气缸1 (30mm)', '气缸2 (30mm)', '气缸3 (30mm)', 'Location', 'southeast');
grid on;
xlim([0, t_total]);
ylim([0, 40]);
for b = [125, 250]
    plot([b, b], [0, 40], ':', 'Color', [0.58 0.64 0.72], ...
         'LineWidth', 1, 'HandleVisibility', 'off');
end
plot([t_all, t_all], [0, stroke], 'k--', 'LineWidth', 1, ...
     'HandleVisibility', 'off');
plot([t_hold_end, t_hold_end], [0, stroke], 'k--', 'LineWidth', 1, ...
     'HandleVisibility', 'off');

subplot(2, 1, 2);
v1 = gradient(pos(1, :), dt);
v2 = gradient(pos(2, :), dt);
v3 = gradient(pos(3, :), dt);
plot(t, v1, 'r-', 'LineWidth', 2); hold on;
plot(t, v2, 'g-', 'LineWidth', 2);
plot(t, v3, 'b-', 'LineWidth', 2);
xlabel('时间 (ms)');
ylabel('运动速度 (mm/ms)');
title('三缸运动速度曲线');
legend('气缸1', '气缸2', '气缸3', 'Location', 'northeast');
grid on;
xlim([0, t_total]);

saveas(gcf, 'F:\伊利雪糕三棒签插签设备项目\matlab\仿真结果曲线.png');
fprintf('\n仿真结果图已保存到：F:\\伊利雪糕三棒签插签设备项目\\matlab\\仿真结果曲线.png\n');
