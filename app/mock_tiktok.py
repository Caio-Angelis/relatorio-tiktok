from __future__ import annotations

from datetime import datetime, timedelta, timezone


class MockTikTokAPI:
    """Deterministic fake API used only with MOCK_TIKTOK=true.

    The application selects a separate *_mock.db path in this mode so these
    records can never be mixed with a real account database by default.
    """

    scopes = "user.info.basic,user.info.stats,video.list"

    def get_user_info(self, access_token: str | None = None) -> dict:
        return {
            "data": {
                "user": {
                    "open_id": "mock-open-id",
                    "display_name": "Relatorio TikTok Demo",
                    "avatar_url": "https://placehold.co/160x160/25f4ee/081011?text=RT",
                    "follower_count": 12840,
                    "following_count": 420,
                    "likes_count": 93210,
                    "video_count": 12,
                }
            }
        }

    def list_videos(self, access_token: str | None = None) -> list[dict]:
        now = datetime.now(timezone.utc)
        videos = []
        descriptions = [
            "Olha o que esse pedal faz em poucos segundos",
            "3 ideias para melhorar seu próximo riff",
            "Comparação rápida: timbre A vs. timbre B",
            "O detalhe que mudou este setup",
            "Tutorial de guitarra para começar hoje",
            "Teste de equipamento com som limpo",
            "Uma dica simples para tocar melhor",
            "Respondendo uma pergunta frequente",
            "Review honesta depois de uma semana",
            "Antes e depois do meu timbre",
            "Como eu gravo uma ideia curta",
            "O erro mais comum neste exercício",
        ]
        for index, description in enumerate(descriptions):
            published = now - timedelta(hours=(index + 1) * 17)
            views = max(750, 26000 - index * 1450)
            videos.append(
                {
                    "id": f"mock-video-{index + 1:02d}",
                    "video_description": description,
                    "title": description[:60],
                    "create_time": int(published.timestamp()),
                    "duration": 18 + (index % 6) * 7,
                    "cover_image_url": f"https://placehold.co/640x360/171a25/25f4ee?text=Video+{index + 1}",
                    "share_url": f"https://www.tiktok.com/@mock/video/mock-video-{index + 1:02d}",
                    "embed_link": f"https://www.tiktok.com/player/v1/mock-video-{index + 1:02d}",
                    "height": 1920,
                    "width": 1080,
                    "like_count": round(views * (0.06 - index * 0.001)),
                    "comment_count": round(views * (0.012 - index * 0.0002)),
                    "share_count": round(views * (0.009 - index * 0.0002)),
                    "view_count": views,
                }
            )
        return videos
