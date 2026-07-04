import csv

# 检查周汇总数据文件
with open('mock_data_weekly_dimension_full.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    rows = list(reader)
    print(f'周汇总维度数据文件:')
    print(f'  总行数: {len(rows)}')
    print(f'  数据行数: {len(rows)-1}')
    print(f'  前5行示例:')
    for i, row in enumerate(rows[:5]):
        print(f'    {i+1}: {row[:8]}...')

# 检查是否有日明细数据文件
try:
    with open('mock_data_daily_trend_full.csv', 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)
        print(f'\n日明细趋势数据文件:')
        print(f'  总行数: {len(rows)}')
        print(f'  数据行数: {len(rows)-1}')
except FileNotFoundError:
    print('\n日明细趋势数据文件: 未生成')