import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from digests.models import Digest

logger = logging.getLogger(__name__)

# Palette de couleurs élégante Dark Cyber/Studio
COLOR_BG = (11, 15, 25)           # Deep Dark Navy
COLOR_CARD = (21, 27, 43)         # Dark Slate Box
COLOR_CARD_BORDER = (45, 55, 80)  # Subtle Slate Border
COLOR_ACCENT = (99, 102, 241)     # Indigo Glow
COLOR_CYAN = (6, 182, 212)        # Cyan Highlight
COLOR_TEXT_WHITE = (248, 250, 252)# Off-white Title
COLOR_TEXT_MUTED = (148, 163, 184)# Slate text
COLOR_BULLET_DOT = (129, 140, 248)# Light Indigo

CATEGORY_COLORS = {
    "tech": (56, 189, 248),      # Light Blue
    "ia": (168, 85, 247),        # Purple
    "startups": (244, 63, 94),   # Rose
    "dev": (34, 197, 94),        # Green
    "finance": (234, 179, 8),    # Amber
}


def _get_font(name: str, size: int):
    candidates = [
        f"/usr/share/fonts/TTF/{name}.ttf",
        f"/usr/share/fonts/dejavu/{name}.ttf",
        f"/usr/share/fonts/truetype/dejavu/{name}.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Découpe un texte pour respecter la largeur maximale en pixels."""
    words = text.split()
    if not words:
        return []

    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []

    if current_line:
        lines.append(" ".join(current_line))

    return lines


def generate_infographic_for_digest(digest: Digest) -> str:
    """
    Génère une carte visuelle / infographie récapitulative haute résolution (1080x1350)
    pour le briefing quotidien et enregistre l'URL dans digest.infographic_url.
    """
    width, height = 1080, 1350
    img = Image.new("RGB", (width, height), color=COLOR_BG)
    draw = ImageDraw.Draw(img)

    # Chargement des polices
    font_brand = _get_font("DejaVuSans-Bold", 46)
    font_badge = _get_font("DejaVuSans-Bold", 20)
    font_date = _get_font("DejaVuSans", 26)
    font_topic_title = _get_font("DejaVuSans-Bold", 30)
    font_body = _get_font("DejaVuSans", 22)
    font_footer = _get_font("DejaVuSans", 20)

    # 1. Bordure décorative & Dégradé supérieur
    draw.rectangle([(0, 0), (width, 8)], fill=COLOR_ACCENT)
    draw.rectangle([(30, 30), (width - 30, height - 30)], outline=COLOR_CARD_BORDER, width=2)

    # 2. En-tête : Logo Synapse & Tag
    draw.text((70, 75), "⚡ SYNAPSE", fill=COLOR_TEXT_WHITE, font=font_brand)
    
    # Badge DAILY BRIEFING
    badge_text = "DAILY DIGEST"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    badge_w = badge_bbox[2] - badge_bbox[0] + 24
    badge_x = width - 70 - badge_w
    draw.rounded_rectangle([(badge_x, 78), (width - 70, 118)], radius=8, fill=(30, 41, 69), outline=COLOR_CYAN, width=1)
    draw.text((badge_x + 12, 88), badge_text, fill=COLOR_CYAN, font=font_badge)

    # Date et sous-titre
    date_str = digest.date.strftime("%d %B %Y")
    draw.text((70, 140), f"Synthèse stratégique du {date_str} • Pour {digest.user.username}", fill=COLOR_TEXT_MUTED, font=font_date)
    draw.line([(70, 185), (width - 70, 185)], fill=COLOR_CARD_BORDER, width=1)

    # 3. Cartes thématiques pour les sujets majeurs (jusqu'à 3 sujets)
    topics = list(digest.topics.order_by("-importance_score")[:3])
    y_cursor = 215
    card_width = width - 140
    card_margin_bottom = 25

    if not topics:
        draw.text((70, 300), "Aucun sujet d'actualité sélectionné.", fill=COLOR_TEXT_MUTED, font=font_body)
    else:
        # Calcul de la hauteur par carte selon le nombre de topics
        num_topics = len(topics)
        card_height = 320 if num_topics == 3 else (450 if num_topics == 2 else 700)

        for idx, topic in enumerate(topics, start=1):
            card_top = y_cursor
            card_bottom = card_top + card_height
            card_box = [(70, card_top), (70 + card_width, card_bottom)]

            # Fond de la carte
            draw.rounded_rectangle(card_box, radius=16, fill=COLOR_CARD, outline=COLOR_CARD_BORDER, width=1)

            # Badge Catégorie
            cat_name = (topic.category or "Actualité").upper()
            cat_color = CATEGORY_COLORS.get(cat_name.lower(), COLOR_CYAN)

            cat_bbox = draw.textbbox((0, 0), cat_name, font=font_badge)
            cat_w = cat_bbox[2] - cat_bbox[0] + 20
            draw.rounded_rectangle([(95, card_top + 25), (95 + cat_w, card_top + 60)], radius=6, fill=(15, 23, 42), outline=cat_color, width=1)
            draw.text((105, card_top + 32), cat_name, fill=cat_color, font=font_badge)

            # Score d'importance
            score_text = f"★ {topic.importance_score}/10"
            draw.text((width - 95 - 90, card_top + 32), score_text, fill=(251, 191, 36), font=font_badge)

            # Titre du sujet
            title_text = topic.title or "Sujet d'actualité"
            title_lines = _wrap_text(title_text, font_topic_title, card_width - 50, draw)
            t_y = card_top + 80
            for line in title_lines[:2]:
                draw.text((95, t_y), line, fill=COLOR_TEXT_WHITE, font=font_topic_title)
                t_y += 38

            # Points clés synthétiques
            bullets = topic.summary_bullets if topic.summary_bullets else []
            b_y = t_y + 15
            for bullet in bullets[:2]:
                if b_y + 40 > card_bottom - 15:
                    break
                # Puce
                draw.ellipse([(98, b_y + 8), (106, b_y + 16)], fill=COLOR_BULLET_DOT)
                # Texte de la puce découpé
                bullet_lines = _wrap_text(bullet, font_body, card_width - 80, draw)
                for bl in bullet_lines[:2]:
                    draw.text((120, b_y), bl, fill=COLOR_TEXT_MUTED, font=font_body)
                    b_y += 30
                b_y += 5

            y_cursor = card_bottom + card_margin_bottom

    # 4. Pied de page
    footer_text = "SYNAPSE INTELLIGENCE • BRIEFING IA SUR MESURE • AUDIO & TEXTE"
    draw.text((70, height - 70), footer_text, fill=(100, 116, 139), font=font_footer)

    # 5. Enregistrement sur disque
    out_dir = Path(settings.MEDIA_ROOT) / "infographics"
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"infographic_{digest.user.username}_{digest.date}.png"
    filepath = out_dir / filename
    img.save(filepath, format="PNG", optimize=True)

    infographic_url = f"{settings.MEDIA_URL}infographics/{filename}"
    digest.infographic_url = infographic_url
    digest.save(update_fields=["infographic_url"])

    return infographic_url
