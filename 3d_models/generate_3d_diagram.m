% 伊利雪糕三棒签同步插签设备 - 3D结构示意图生成
% 用Matlab生成设备结构示意图

clear; clc; close all;

figure('Position', [100, 100, 1000, 700]);
ax = gca;
hold on;
grid on;

% ========== 绘制机架 ==========
% 机架底部
plot3([0, 100, 100, 0, 0], [0, 0, 60, 60, 0], [0, 0, 0, 0, 0], 'k-', 'LineWidth', 3);

% 机架立柱
for x = [0, 100]
    for y = [0, 60]
        plot3([x, x], [y, y], [0, 80], 'k-', 'LineWidth', 2);
    end
end

% ========== 绘制三个气缸 ==========
cylinder_x = [20, 50, 80];
cylinder_colors = ['r', 'g', 'b'];
cylinder_names = {'气缸1 (30mm)', '气缸2 (45mm)', '气缸3 (60mm)'};

for i = 1:3
    x = cylinder_x(i);
    % 气缸缸筒
    fill3([x-5, x+5, x+5, x-5], [25, 25, 35, 35], [60, 60, 60, 60], cylinder_colors(i), 'FaceAlpha', 0.7);
    % 气缸推杆
    fill3([x-2, x+2, x+2, x-2], [27, 27, 33, 33], [40, 40, 40, 40], [0.5, 0.5, 0.5], 'FaceAlpha', 0.8);
end

% ========== 绘制雪糕模具 ==========
fill3([15, 85, 85, 15], [20, 20, 40, 40], [30, 30, 30, 30], [1, 0.6, 0], 'FaceAlpha', 0.5);

% ========== 绘制电磁阀组 ==========
fill3([102, 107, 107, 102], [10, 10, 50, 50], [20, 20, 20, 20], [0.5, 0, 0.5], 'FaceAlpha', 0.6);

% ========== 设置坐标轴 ==========
xlabel('X (mm)', 'FontSize', 12);
ylabel('Y (mm)', 'FontSize', 12);
zlabel('Z (mm)', 'FontSize', 12);
title('伊利雪糕三棒签同步插签设备 - 3D结构示意图', 'FontSize', 14);

xlim([0, 110]);
ylim([0, 70]);
zlim([0, 90]);

% 添加图例
legend('机架', '气缸1', '气缸2', '气缸3', '雪糕模具', '电磁阀组', 'Location', 'northeast');

% 添加说明文字
info_text = sprintf(['工作原理：\n', ...
    '- 三缸行程统一 30mm（木签三根同长）\n', ...
    '- 错峰启动 0/125/250ms（相邻错峰 125ms）\n', ...
    '- 三缸于 200/325/450ms 依次到位\n', ...
    '- 实现三根棒签同步插入雪糕']);
text(5, 5, 85, info_text, 'FontSize', 10, 'BackgroundColor', [1, 0.9, 0.6], 'EdgeColor', [0.8, 0.6, 0.2]);

view(30, 30);  % 设置视角

% 保存图片
saveas(gcf, 'F:\伊利雪糕三棒签插签设备项目\3d_models\设备3D结构示意图.png');
disp('3D结构示意图已生成：设备3D结构示意图.png');
