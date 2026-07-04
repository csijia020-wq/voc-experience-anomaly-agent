import csv

def check_detailed_time_range():
    """详细检查时间范围"""

    # 检查 mock_data_weekly_dimension_full.csv
    print("="*60)
    print("详细检查 mock_data_weekly_dimension_full.csv")
    print("="*60)

    with open('mock_data_weekly_dimension_full.csv', 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    weeks_2025 = set()
    weeks_2026 = set()
    for row in rows:
        year = row['年份']
        week = row['周次']
        if year == '2025':
            weeks_2025.add(week)
        elif year == '2026':
            weeks_2026.add(week)

    print(f"2025年周次数量: {len(weeks_2025)}")
    print(f"2025年周次列表: {sorted(weeks_2025, key=lambda x: int(x[1:]))}")

    print(f"\n2026年周次数量: {len(weeks_2026)}")
    print(f"2026年周次列表: {sorted(weeks_2026, key=lambda x: int(x[1:]))}")

    print(f"\n总周次数量: {len(weeks_2025) + len(weeks_2026)}")

    # 检查 mock_data_daily_trend_full.csv
    print("\n" + "="*60)
    print("详细检查 mock_data_daily_trend_full.csv")
    print("="*60)

    with open('mock_data_daily_trend_full.csv', 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    weeks_2025 = set()
    weeks_2026 = set()
    for row in rows:
        year = row['年份']
        week = row['周次']
        if year == '2025':
            weeks_2025.add(week)
        elif year == '2026':
            weeks_2026.add(week)

    print(f"2025年周次数量: {len(weeks_2025)}")
    print(f"2026年周次数量: {len(weeks_2026)}")
    print(f"总周次数量: {len(weeks_2025) + len(weeks_2026)}")

    # 检查 mock_data_time_range.csv
    print("\n" + "="*60)
    print("详细检查 mock_data_time_range.csv")
    print("="*60)

    with open('mock_data_time_range.csv', 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    weeks_2025 = set()
    weeks_2026 = set()
    for row in rows:
        year = row['年份']
        week = row['周次']
        if year == '2025':
            weeks_2025.add(week)
        elif year == '2026':
            weeks_2026.add(week)

    print(f"2025年周次数量: {len(weeks_2025)}")
    print(f"2026年周次数量: {len(weeks_2026)}")
    print(f"总周次数量: {len(weeks_2025) + len(weeks_2026)}")

    print("\n" + "="*60)
    print("结论")
    print("="*60)
    print(f"预期总周次: 78周 (2025年52周 + 2026年26周)")
    print(f"mock_data_weekly_dimension_full.csv: {len(weeks_2025) + len(weeks_2026)}周")
    print(f"mock_data_daily_trend_full.csv: {len(weeks_2025) + len(weeks_2026)}周")
    print(f"mock_data_time_range.csv: {len(weeks_2025) + len(weeks_2026)}周")

check_detailed_time_range()
