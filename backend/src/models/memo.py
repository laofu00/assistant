"""备忘录 ORM 模型"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class Memo(Base):
    __tablename__ = "memo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20), default="未分类")
    status: Mapped[int] = mapped_column(Integer, default=1)  # 1:正常 0:删除 2:完成
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Memo(id={self.id}, title='{self.title}', status={self.status})>"


# 自动分类规则 — 按关键词长度降序匹配，长词优先避免歧义
CATEGORY_RULES: dict[str, str] = {
    # ========== 工作 ==========
    "代码审查": "工作", "代码评审": "工作", "code review": "工作",
    "技术方案": "工作", "设计文档": "工作",
    "面试": "工作", "培训": "工作", "团建": "工作", "年会": "工作",
    "周报": "工作", "日报": "工作", "月报": "工作", "述职": "工作",
    "okr": "工作", "kpi": "工作", "绩效": "工作",
    "会议": "工作", "开会": "工作", "讨论": "工作", "汇报": "工作",
    "项目": "工作", "需求": "工作", "排期": "工作", "迭代": "工作",
    "发布": "工作", "上线": "工作", "部署": "工作", "发版": "工作",
    "hotfix": "工作", "patch": "工作", "版本": "工作",
    "出差": "工作", "客户": "工作", "合同": "工作", "报价": "工作",
    "招标": "工作", "供应商": "工作", "外包": "工作",
    "演示": "工作", "demo": "工作",
    "报销": "工作", "审批": "工作", "预算": "工作",
    "运维": "工作", "监控": "工作", "告警": "工作",
    "bug": "工作", "修复": "工作", "测试": "工作",
    "入职": "工作", "离职": "工作", "转正": "工作",
    "请假": "工作", "年假": "工作", "调休": "工作", "加班": "工作",
    "门禁": "工作", "工牌": "工作", "工位": "工作",
    "接口": "工作", "api": "工作", "sql": "工作", "数据库": "工作",
    "前端": "工作", "后端": "工作", "小程序": "工作",
    "审计": "工作", "值班": "工作", "排班": "工作",
    "工资": "工作", "薪资": "工作", "考评": "工作",
    "报告": "工作", "交报告": "工作", "交作业": "工作",
    # ========== 生活 ==========
    "保险续保": "生活", "份子钱": "生活",
    "演唱会": "生活", "博物馆": "生活", "展览": "生活", "看电影": "生活",
    "广场舞": "生活", "羽毛球": "生活", "乒乓球": "生活",
    "大扫除": "生活", "公积金": "生活", "配眼镜": "生活",
    "过户": "生活", "乔迁": "生活",
    "驾照": "生活", "违章": "生活", "年检": "生活",
    "生日": "生活", "聚会": "生活", "聚餐": "生活",
    "搬家": "生活", "装修": "生活", "家具": "生活", "家电": "生活",
    "旅游": "生活", "出行": "生活", "爬山": "生活", "露营": "生活",
    "自驾": "生活",
    "理发": "生活", "看病": "生活", "体检": "生活", "挂号": "生活",
    "健身": "生活", "跑步": "生活", "游泳": "生活", "瑜伽": "生活",
    "打球": "生活", "篮球": "生活", "足球": "生活",
    "宠物": "生活", "遛狗": "生活", "猫粮": "生活", "狗粮": "生活",
    "养花": "生活", "做饭": "生活", "菜谱": "生活",
    "外卖": "生活", "快递": "生活", "购物": "生活", "买菜": "生活",
    "春节": "生活", "中秋": "生活", "端午": "生活", "国庆": "生活",
    "婚礼": "生活", "结婚": "生活", "随礼": "生活",
    "修车": "生活", "洗车": "生活", "保养": "生活", "加油": "生活",
    "物业": "生活", "水电": "生活", "燃气": "生活", "宽带": "生活",
    "wifi": "生活", "网费": "生活", "电话费": "生活",
    "干洗": "生活", "换季": "生活", "洗衣": "生活",
    "维修": "生活", "牙医": "生活",
    "扫除": "生活", "社保": "生活", "医保": "生活",
    # ========== 学习 ==========
    "毕业设计": "学习", "思维导图": "学习", "知识体系": "学习",
    "设计模式": "学习", "系统设计": "学习",
    "读后感": "学习", "公开课": "学习", "视频课": "学习",
    "背单词": "学习", "leetcode": "学习",
    "考证": "学习", "考研": "学习",
    "cpa": "学习", "cfa": "学习", "pmp": "学习",
    "雅思": "学习", "托福": "学习",
    "学习": "学习", "读书": "学习", "阅读": "学习", "课程": "学习",
    "作业": "学习", "笔记": "学习", "总结": "学习", "复习": "学习",
    "考试": "学习", "论文": "学习", "答辩": "学习", "开题": "学习",
    "刷题": "学习", "打卡": "学习", "练习": "学习",
    "教程": "学习", "tutorial": "学习",
    "编程": "学习", "coding": "学习", "算法": "学习", "架构": "学习",
    "翻译": "学习", "英语": "学习", "日语": "学习",
    "书单": "学习", "书评": "学习",
    "乐器": "学习", "钢琴": "学习", "吉他": "学习", "练字": "学习",
    "录播": "学习", "网课": "学习",
    # ========== 待办 ==========
    "别忘了": "待办", "不要忘": "待办",
    "deadline": "待办", "ddl": "待办", "最后期限": "待办",
    "信用卡": "待办", "寄快递": "待办",
    "记得": "待办", "备忘": "待办",
    "提醒": "待办", "todo": "待办", "待办": "待办", "任务": "待办",
    "完成": "待办", "跟一下": "待办", "跟进": "待办",
    "检查": "待办", "确认": "待办", "联系": "待办", "回复": "待办",
    "处理": "待办", "整理": "待办", "清理": "待办",
    "缴费": "待办", "还款": "待办", "还钱": "待办", "交费": "待办",
    "填写": "待办", "提交": "待办", "上传": "待办", "下载": "待办",
    "打印": "待办", "复印": "待办", "扫描": "待办", "邮寄": "待办",
    "安装": "待办", "卸载": "待办", "升级": "待办", "更新": "待办",
    "取件": "待办", "取快递": "待办",
    "买药": "待办",
    # ========== 重要 ==========
    "第一时间": "重要", "优先级高": "重要", "high priority": "重要",
    "asap": "重要",
    "重要": "重要", "紧急": "重要", "尽快": "重要", "截止": "重要",
    "必须": "重要", "务必": "重要", "马上": "重要", "立即": "重要",
    "p0": "重要", "p1": "重要",
}

# 按关键词长度降序排列：长词优先匹配，避免"测试题"被"测试"误判
_SORTED_KEYWORDS: list[str] = sorted(CATEGORY_RULES.keys(), key=len, reverse=True)

CATEGORY_LIST = ["工作", "生活", "待办", "学习", "重要"]


def classify_memo(title: str, content: str | None = None) -> str:
    """根据标题和内容自动分类（重要优先 + 最长优先）"""
    text = f"{title or ''} {content or ''}".lower()
    # 第一遍：重要关键词优先，不受长度影响（"紧急" > "bug"）
    for keyword in _SORTED_KEYWORDS:
        if CATEGORY_RULES[keyword] == "重要" and keyword.lower() in text:
            return "重要"
    # 第二遍：其他分类按长词优先
    for keyword in _SORTED_KEYWORDS:
        if CATEGORY_RULES[keyword] != "重要" and keyword.lower() in text:
            return CATEGORY_RULES[keyword]
    return "未分类"


async def async_classify_memo(title: str, content: str | None = None) -> str:
    """异步分类：先关键词匹配，失败则 LLM 语义回退"""
    category = classify_memo(title, content)
    if category != "未分类":
        return category

    # LLM 回退 — 懒加载避免模型层依赖
    from loguru import logger
    try:
        from langchain_community.chat_models.tongyi import ChatTongyi
        from langchain_core.messages import HumanMessage, SystemMessage
        from src.core.config import settings

        llm = ChatTongyi(
            model=settings.MODEL_NAME,
            dashscope_api_key=settings.OPENAI_API_KEY,
            temperature=0,
        )
        prompt_text = f"标题：{title}\n内容：{content or ''}"
        response = await llm.ainvoke([
            SystemMessage(
                content="你是一个备忘录分类助手。将以下备忘录分到最合适的类别："
                        "工作、生活、待办、学习、重要。只输出分类名称，不要加任何解释。"
            ),
            HumanMessage(content=prompt_text),
        ])
        llm_category = response.content.strip()
        if llm_category in CATEGORY_LIST:
            logger.info(f"LLM 分类: \"{title}\" → {llm_category}")
            return llm_category
        logger.debug(f"LLM 分类返回无效值: {llm_category}")
    except Exception as e:
        logger.warning(f"LLM 分类失败: {e}")

    return "未分类"
