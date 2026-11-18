"""
伊利雪糕三棒签同步插签设备 - 3D结构示意图生成
用matplotlib生成设备结构示意图
"""
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

fig = plt.figure(figsize=(12, 8))
ax = fig.add_subplot(111, projection='3d')

# ========== 绘制机架 ==========
# 机架底部（铝型材框架）
frame_x = [0, 100, 100, 0, 0]
frame_y = [0, 0, 60, 60, 0]
frame_z = [0, 0, 0, 0, 0]
ax.plot(frame_x, frame_y, frame_z, 'k-', linewidth=3, label='机架（铝型材）')

# 机架立柱
for x in [0, 100]:
    for y in [0, 60]:
        ax.plot([x, x], [y, y], [0, 80], 'k-', linewidth=2)

# ========== 绘制三个气缸 ==========
# 气缸位置（X方向三个）
cylinder_positions = [20, 50, 80]  # X坐标
cylinder_colors = ['red', 'green', 'blue']
cylinder_names = ['气缸1 (30mm)', '气缸2 (45mm)', '气缸3 (60mm)']

for i, x in enumerate(cylinder_positions):
    # 气缸缸筒（圆柱体简化为矩形）
    ax.bar3d(x-5, 25, 60, 10, 10, 20, color=cylinder_colors[i], alpha=0.7, label=cylinder_names[i])
    
    # 气缸推杆
    ax.bar3d(x-2, 27, 40, 4, 6, 20, color='gray', alpha=0.8)

# ========== 绘制雪糕模具 ==========
# 雪糕模具定位工装
ax.bar3d(15, 20, 30, 70, 20, 5, color='orange', alpha=0.5, label='雪糕模具定位工装')

# ========== 绘制电磁阀组 ==========
# 电磁阀组（机架侧面）
ax.bar3d(102, 10, 20, 5, 40, 30, color='purple', alpha=0.6, label='电磁阀组')

# ========== 设置坐标轴 ==========
ax.set_xlabel('X (mm)', fontsize=12)
ax.set_ylabel('Y (mm)', fontsize=12)
ax.set_zlabel('Z (mm)', fontsize=12)
ax.set_title('伊利雪糕三棒签同步插签设备 - 3D结构示意图', fontsize=14, pad=20)

# 设置坐标范围
ax.set_xlim(0, 110)
ax.set_ylim(0, 70)
ax.set_zlim(0, 90)

# 添加图例
ax.legend(loc='upper left', fontsize=9)

# 添加说明文字
info_text = """
工作原理：
- 三缸行程统一 30mm（木签三根同长）
- 错峰启动 0/125/250ms（相邻错峰 125ms）
- 三缸于 200/325/450ms 依次到位
- 实现三根棒签同步插入雪糕
"""
ax.text2D(0.02, 0.02, info_text, transform=ax.transAxes, fontsize=10,
          bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

plt.tight_layout()
plt.savefig('F:/伊利雪糕三棒签插签设备项目/3d_models/设备3D结构示意图.png', dpi=150, bbox_inches='tight')
print("3D结构示意图已生成：设备3D结构示意图.png")
plt.show()
