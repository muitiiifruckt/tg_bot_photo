import json
import os
from typing import Dict, List, Optional


class ModelsManager:
    """Менеджер для работы с моделями и ценами"""
    
    def __init__(self, config_file: str = "models_pricing.json"):
        self.config_file = config_file
        self.models = []
        self.default_model = None
        self._load_config()
    
    def _load_config(self):
        """Загрузка конфигурации из JSON файла"""
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Файл конфигурации моделей не найден: {self.config_file}")
        
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.models = config.get("models", [])
            self.default_model = config.get("default_model")
    
    def get_model_by_name(self, openrouter_name: str) -> Optional[Dict]:
        """Получить модель по имени в OpenRouter"""
        for model in self.models:
            if model["openrouter_name"] == openrouter_name:
                return model
        return None
    
    def get_enabled_models(self) -> List[Dict]:
        """Получить список доступных моделей"""
        return [model for model in self.models if model.get("enabled", False)]
    
    def get_model_price(self, openrouter_name: str) -> int:
        """Получить цену генерации для модели (в рубинах)"""
        model = self.get_model_by_name(openrouter_name)
        if model:
            return model.get("price_rubies", 2)
        return 2  # Цена по умолчанию
    
    def get_default_model(self) -> Dict:
        """Получить модель по умолчанию"""
        if self.default_model:
            model = self.get_model_by_name(self.default_model)
            if model:
                return model
        
        # Если модель по умолчанию не найдена, возвращаем первую доступную
        enabled = self.get_enabled_models()
        if enabled:
            return enabled[0]
        
        # Если нет доступных моделей, возвращаем первую из списка
        if self.models:
            return self.models[0]
        
        return None
    
    def get_models_list_text(self) -> str:
        """Получить текстовое описание доступных моделей для пользователя"""
        enabled = self.get_enabled_models()
        
        if not enabled:
            return "🚫 Нет доступных моделей"
        
        text = "🎨 Доступные модели:\n\n"
        for model in enabled:
            text += f"🤖 {model['display_name']}\n"
            text += f"   {model['description']}\n"
            text += f"   💎 Цена: {model['price_rubies']} рубин{'ов' if model['price_rubies'] > 1 else ''}\n\n"
        
        return text
    
    def reload_config(self):
        """Перезагрузить конфигурацию из файла"""
        self._load_config()
