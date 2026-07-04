"""
Skill加载器 - 读取skill文件内容供Agent使用
"""
import os
from typing import Dict, Optional


class SkillLoader:
    """Skill文件加载器"""

    def __init__(self, skills_dir: str = None):
        if skills_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.skills_dir = os.path.join(base_dir, "skills")
        else:
            self.skills_dir = skills_dir

        self._cache: Dict[str, str] = {}

    def load_skill(self, skill_name: str) -> Optional[str]:
        """
        加载指定skill文件内容

        Args:
            skill_name: skill文件名（不含.md后缀）

        Returns:
            skill文件内容，如果不存在返回None
        """
        if skill_name in self._cache:
            return self._cache[skill_name]

        skill_path = os.path.join(self.skills_dir, f"{skill_name}.md")

        if not os.path.exists(skill_path):
            return None

        try:
            with open(skill_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self._cache[skill_name] = content
            return content
        except Exception as e:
            print(f"[ERROR] Failed to load skill {skill_name}: {e}")
            return None

    def get_skill_for_llm(self, skill_name: str, role: str = None) -> str:
        """
        获取适合LLM使用的skill内容

        Args:
            skill_name: skill名称
            role: 可选的角色描述

        Returns:
            格式化的skill内容
        """
        content = self.load_skill(skill_name)
        if content is None:
            return ""

        if role:
            return f"【{role}】\n\n{content}"
        return content

    def get_all_skills_content(self) -> str:
        """获取所有skill内容拼接"""
        skills = [
            ("friday-mcp-query", "数据查询"),
            ("experience-anomaly-report", "异动分析"),
            ("scheduled-message", "定时任务"),
            ("s3plus-upload", "报告上传")
        ]

        parts = []
        for skill_name, role in skills:
            content = self.load_skill(skill_name)
            if content:
                parts.append(f"【{role} Skill】\n\n{content}\n\n{'='*50}\n")

        return "\n".join(parts)

    def list_skills(self) -> list:
        """列出所有可用的skill"""
        if not os.path.exists(self.skills_dir):
            return []

        return [
            f[:-3] for f in os.listdir(self.skills_dir)
            if f.endswith('.md')
        ]


# 单例实例
skill_loader = SkillLoader()
