from openai import OpenAI

from tg_bot.core.config import OPENROUTER_API_KEY, OPENROUTER_MODEL

import base64


class OpenRouterClient:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        self.model = OPENROUTER_MODEL

    def encode_image_to_base64(self, image_bytes: bytes) -> str:
        """Кодирование изображения в base64"""
        return base64.b64encode(image_bytes).decode("utf-8")

    async def generate_image(self, prompt: str, input_image: bytes = None, input_images: list = None, model: str = None):
        """Генерация изображения по промпту, опционально на основе входного изображения или нескольких изображений"""
        model_to_use = model if model else self.model

        try:
            if input_images:
                content = []
                for img_bytes in input_images:
                    base64_image = self.encode_image_to_base64(img_bytes)
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        }
                    )
                content.append({"type": "text", "text": prompt})
            elif input_image:
                base64_image = self.encode_image_to_base64(input_image)
                content = [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                    {
                        "type": "text",
                        "text": f"Создай новое изображение на основе этого, учитывая следующее описание: {prompt}",
                    },
                ]
            else:
                content = prompt

            response = self.client.chat.completions.create(
                model=model_to_use,
                messages=[{"role": "user", "content": content}],
                extra_body={"modalities": ["image", "text"]},
            )

            message = response.choices[0].message

            if hasattr(message, "images") and message.images:
                if isinstance(message.images, list) and len(message.images) > 0:
                    image_data = message.images[0]
                    if isinstance(image_data, dict) and "image_url" in image_data:
                        return image_data["image_url"]["url"]
                    if isinstance(image_data, str):
                        return image_data

            if hasattr(message, "content") and message.content:
                if isinstance(message.content, list):
                    for part in message.content:
                        if hasattr(part, "type") and part.type == "image_url":
                            if hasattr(part, "image_url") and hasattr(part.image_url, "url"):
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
            _, encoded = data_url.split(",", 1)
            return base64.b64decode(encoded)
        return None

