import csv
import os

def check_csv_file(filepath):
    """检查CSV文件的基本信息"""
    print(f"\n{'='*60}")
    print(f"文件: {filepath}")
    print(f"{'='*60}")

    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            print("  [错误] 文件为空")
            return

        # 表头
        header = rows[0]
        print(f"表头 ({len(header)}列):")
        for i, col in enumerate(header):
            print(f"  {i+1}. {col}")

        # 数据行数
        data_rows = len(rows) - 1
        print(f"\n数据行数: {data_rows}")

        # 前3行示例
        print(f"\n前3行示例:")
        for i, row in enumerate(rows[1:4], 1):
            print(f"  行{i}: {row[:6]}{'...' if len(row) > 6 else ''}")

        # 检查是否有结论性字段
        conclusion_keywords = ['校验结果', '校验说明', '异动标签', '告警类型', '处置建议', '告警描述']
        has_conclusion = False
        for keyword in conclusion_keywords:
            if keyword in header:
                print(f"\n  [警告] 发现结论性字段: {keyword}")
                has_conclusion = True

        if not has_conclusion:
            print(f"\n  [通过] 未发现结论性字段")

        return header, data_rows

    except Exception as e:
        print(f"  [错误] {e}")
        return None, 0

def check_time_range(filepath):
    """检查时间范围"""
    print(f"\n时间范围检查:")

    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            print("  [错误] 文件为空")
            return

        # 查找年份/周次字段
        first_row = rows[0]

        if '年份' in first_row and '周次' in first_row:
            years = set()
            weeks = set()
            for row in rows:
                years.add(row['年份'])
                weeks.add(row['周次'])
            print(f"  年份范围: {sorted(years)}")
            print(f"  周次示例: {sorted(weeks)[:5]}... (共{len(weeks)}个周次)")
            return years, weeks

        if '日期' in first_row:
            dates = [row['日期'] for row in rows[:100]]
            print(f"  日期示例: {dates[:3]}...")
            return dates

        return None, None

    except Exception as e:
        print(f"  [错误] {e}")
        return None, None

def check_field_alignment():
    """检查字段对齐情况"""
    print("\n\n" + "="*60)
    print("字段对齐检查（对比Skill定义）")
    print("="*60)

    # Skill定义的字段
    skill_fields = {
        '周汇总数据': ['业务名称', '维度类型', '维度值', '服务量', '订单量', '万服', 'YoY%', '贡献度%'],
        '日明细数据': ['业务名称', '日期', '服务量', '订单量', '万服', 'YoY%'],
        '维度可用性': ['业务名称', '维度类型', '维度值', 'available'],
        '元数据': ['业务名称', '数据集ID', '查询时间戳']
    }

    for name, fields in skill_fields.items():
        print(f"\n{name}应有字段: {', '.join(fields)}")

def main():
    print("="*60)
    print("CSV数据文件全面检查")
    print("="*60)

    # 列出所有CSV文件
    csv_files = [f for f in os.listdir('.') if f.endswith('.csv')]

    print(f"\n找到 {len(csv_files)} 个CSV文件:")
    for f in csv_files:
        print(f"  - {f}")

    # 检查每个文件
    all_headers = {}
    for filepath in csv_files:
        header, rows = check_csv_file(filepath)
        if header:
            all_headers[filepath] = header

        # 检查时间范围
        if 'time_range' in filepath or 'daily_trend_full' in filepath or 'weekly_dimension_full' in filepath:
            check_time_range(filepath)

    # 字段对齐检查
    check_field_alignment()

    print("\n\n" + "="*60)
    print("检查完成")
    print("="*60)

main()
