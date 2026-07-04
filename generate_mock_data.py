import csv
import random
from datetime import datetime, timedelta

# 定义业务和维度
businesses = ['到餐客服', '闪购客服', '企客业务']

dimensions = {
    '城市等级': ['一线城市', '二线城市', '三线城市', '四线城市', '五线城市'],
    '品类': {
        '到餐客服': ['外卖', '到店', '酒旅', '闪购', '优选'],
        '闪购客服': ['生鲜果蔬', '鲜花绿植', '医药健康', '日用百货', '酒水饮料'],
        '企客业务': ['企业外卖', '企业团购', '企业定制']
    },
    '事件类别': {
        '到餐客服': ['配送问题', '退款问题', '质量问题', '服务态度', '优惠券问题', '账户问题', '支付问题', '会员服务'],
        '闪购客服': ['配送问题', '退款问题', '质量问题', '服务态度', '优惠券问题'],
        '企客业务': ['配送问题', '退款问题', '企业专属']
    },
    '进线渠道': ['APP在线', '电话热线', '小程序', '网页端'],
    '战区': ['华东战区', '华南战区', '华北战区', '华中战区', '西南战区', '西北战区'],
    'FAQ': {
        '到餐客服': ['配送时效咨询', '退款进度查询', '优惠券使用', '会员权益', '积分兑换'],
        '闪购客服': ['配送时效咨询', '退款进度查询', '优惠券使用'],
        '企客业务': ['配送时效咨询', '退款进度查询']
    }
}

# 定义时间范围
def get_week_ranges():
    """生成2025年全年和2026年上半年的周次范围"""
    weeks = []
    
    # 2025年W1-W52
    start_date_2025_w1 = datetime(2025, 1, 6)  # 2025年W1开始
    for week_num in range(1, 53):
        week_start = start_date_2025_w1 + timedelta(weeks=week_num-1)
        week_end = week_start + timedelta(days=6)
        weeks.append({
            'year': 2025,
            'week': f'W{week_num}',
            'start': week_start.strftime('%Y-%m-%d'),
            'end': week_end.strftime('%Y-%m-%d'),
            'type': '历史对比期'
        })
    
    # 2026年W1-W26
    start_date_2026_w1 = datetime(2025, 12, 29)  # 2026年W1开始（跨年周）
    for week_num in range(1, 27):
        week_start = start_date_2026_w1 + timedelta(weeks=week_num-1)
        week_end = week_start + timedelta(days=6)
        week_type = '本期重点分析' if week_num == 12 else '当前分析期'
        weeks.append({
            'year': 2026,
            'week': f'W{week_num}',
            'start': week_start.strftime('%Y-%m-%d'),
            'end': week_end.strftime('%Y-%m-%d'),
            'type': week_type
        })
    
    return weeks

# 生成随机数据
def generate_service_data(base_service, base_order):
    """生成服务量和订单量数据"""
    service = int(base_service * random.uniform(0.8, 1.2))
    order = int(base_order * random.uniform(0.8, 1.2))
    wanfu = round(service / order * 10000, 2)
    return service, order, wanfu

# 生成异动标签
def generate_tags(yoy, prev_service, curr_service):
    """根据YoY和历史数据生成异动标签"""
    tags = []
    
    # 近零增长判断
    if prev_service < 10 and curr_service > 100:
        tags.append('new_actual')
    
    # 极端值判断
    if abs(yoy) > 500 and prev_service >= 10:
        tags.append('extreme_value')
    
    # 主要推高/压低判断
    if yoy > 5:
        tags.append('up_major')
    elif yoy < -5:
        tags.append('down_major')
    
    return tags[0] if tags else ''

# 生成CSV数据
def generate_weekly_dimension_data():
    """生成周汇总维度分析数据"""
    weeks = get_week_ranges()
    
    with open('mock_data_weekly_dimension_full.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            '业务名称', '年份', '周次', '开始日期', '结束日期', '周类型',
            '维度类型', '维度值',
            '本期服务量', '本期订单量', '本期万服',
            '对比期服务量', '对比期订单量', '对比期万服',
            '绝对差(delta)', 'YoY%', '贡献度%', '次/万单贡献', '异动标签'
        ])
        
        for business in businesses:
            for week in weeks:
                # 为每个维度生成数据
                for dim_type, dim_values in dimensions.items():
                    # 处理不同业务的维度差异
                    if isinstance(dim_values, dict):
                        values = dim_values.get(business, [])
                    else:
                        values = dim_values
                    
                    for dim_value in values:
                        # 生成基础数据（根据业务和维度调整）
                        if business == '到餐客服':
                            base_service = random.randint(1000, 25000)
                            base_order = random.randint(50000, 1500000)
                        elif business == '闪购客服':
                            base_service = random.randint(500, 10000)
                            base_order = random.randint(30000, 500000)
                        else:  # 企客业务
                            base_service = random.randint(200, 5000)
                            base_order = random.randint(10000, 250000)
                        
                        # 本期数据
                        curr_service, curr_order, curr_wanfu = generate_service_data(base_service, base_order)
                        
                        # 对比期数据（去年同期）
                        prev_service, prev_order, prev_wanfu = generate_service_data(base_service * 0.95, base_order * 0.95)
                        
                        # 计算指标
                        delta = round(curr_wanfu - prev_wanfu, 2)
                        yoy = round((curr_wanfu - prev_wanfu) / prev_wanfu * 100, 2) if prev_wanfu != 0 else 0
                        contrib = round(random.uniform(-5, 25), 2)  # 贡献度%
                        contrib_wanfu = round(delta * contrib / 100, 2)  # 次/万单贡献
                        
                        # 生成异动标签
                        tag = generate_tags(yoy, prev_service, curr_service)
                        
                        # 写入数据
                        writer.writerow([
                            business, week['year'], week['week'], week['start'], week['end'], week['type'],
                            dim_type, dim_value,
                            curr_service, curr_order, curr_wanfu,
                            prev_service, prev_order, prev_wanfu,
                            delta, yoy, contrib, contrib_wanfu, tag
                        ])

def generate_daily_trend_data():
    """生成日明细趋势数据"""
    weeks = get_week_ranges()
    
    with open('mock_data_daily_trend_full.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            '业务名称', '年份', '周次', '日期',
            '本期服务量', '本期订单量', '本期万服',
            '对比期服务量', '对比期订单量', '对比期万服',
            '绝对差(delta)', 'YoY%'
        ])
        
        for business in businesses:
            for week in weeks:
                # 生成7天的日数据
                week_start = datetime.strptime(week['start'], '%Y-%m-%d')
                for day_offset in range(7):
                    date = (week_start + timedelta(days=day_offset)).strftime('%Y-%m-%d')
                    
                    # 生成基础数据
                    if business == '到餐客服':
                        base_service = random.randint(2000, 25000)
                        base_order = random.randint(100000, 1500000)
                    elif business == '闪购客服':
                        base_service = random.randint(800, 10000)
                        base_order = random.randint(40000, 500000)
                    else:
                        base_service = random.randint(300, 5000)
                        base_order = random.randint(15000, 250000)
                    
                    # 本期数据
                    curr_service, curr_order, curr_wanfu = generate_service_data(base_service, base_order)
                    
                    # 对比期数据
                    prev_service, prev_order, prev_wanfu = generate_service_data(base_service * 0.95, base_order * 0.95)
                    
                    # 计算指标
                    delta = round(curr_wanfu - prev_wanfu, 2)
                    yoy = round((curr_wanfu - prev_wanfu) / prev_wanfu * 100, 2) if prev_wanfu != 0 else 0
                    
                    writer.writerow([
                        business, week['year'], week['week'], date,
                        curr_service, curr_order, curr_wanfu,
                        prev_service, prev_order, prev_wanfu,
                        delta, yoy
                    ])

# 执行生成
print("开始生成完整Mock数据...")
generate_weekly_dimension_data()
print("已生成 mock_data_weekly_dimension_full.csv")

generate_daily_trend_data()
print("已生成 mock_data_daily_trend_full.csv")

print("\n数据生成完成！")
print("- 周汇总维度数据：约{}条记录".format(len(businesses) * 78 * 40))
print("- 日明细趋势数据：约{}条记录".format(len(businesses) * 78 * 7))