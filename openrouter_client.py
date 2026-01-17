from openai import OpenAI
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL
import base64
import io


class OpenRouterClient:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        self.model = OPENROUTER_MODEL

    def encode_image_to_base64(self, image_bytes: bytes) -> str:
        """Кодирование изображения в base64"""
        return base64.b64encode(image_bytes).decode('utf-8')

    async def generate_image(self, prompt: str, input_image: bytes = None):
        """Генерация изображения по промпту, опционально на основе входного изображения"""
        try:
            # Формируем контент сообщения
            if input_image:
                # Если есть входное изображение, формируем multimodal content
                base64_image = self.encode_image_to_base64(input_image)
                content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    },
                    {
                        "type": "text",
                        "text": f"Создай новое изображение на основе этого, учитывая следующее описание: {prompt}"
                    }
                ]
            else:
                # Обычная генерация по тексту
                content = prompt
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": content
                    }
                ],
                extra_body={"modalities": ["image", "text"]}
            )

            # Получаем изображение из ответа
            message = response.choices[0].message
            
            # Проверяем наличие изображений в разных форматах
            if hasattr(message, 'images') and message.images:
                # Формат: message.images[0]['image_url']['url']
                if isinstance(message.images, list) and len(message.images) > 0:
                    image_data = message.images[0]
                    if isinstance(image_data, dict) and 'image_url' in image_data:
                        image_url = image_data['image_url']['url']
                        return image_url
                    elif isinstance(image_data, str):
                        return image_data
            
            # Проверяем content для изображений
            if hasattr(message, 'content') and message.content:
                if isinstance(message.content, list):
                    # Если content - список частей
                    for part in message.content:
                        if hasattr(part, 'type') and part.type == 'image_url':
                            if hasattr(part, 'image_url') and hasattr(part.image_url, 'url'):
                                return part.image_url.url
                elif isinstance(message.content, str) and message.content.startswith("data:image"):
                    return message.content
            
            return None
        except Exception as e:
            print(f"Error generating image: {e}")
            import traceback
            traceback.print_exc()
            return None

    def decode_base64_image(self, data_url: str) -> bytes:
        """Декодирование base64 изображения из data URL"""
        if data_url.startswith("data:image"):
            # Формат: data:image/png;base64,<base64_data>
            header, encoded = data_url.split(",", 1)
            image_data = base64.b64decode(encoded)
            return image_data
        return None
