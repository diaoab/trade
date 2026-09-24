"""Palettes de couleurs personnalisables pour l'apparence de l'app.

Le thème de base (fond sombre, rayons arrondis, typographie) reste défini
dans .streamlit/config.toml et ne peut pas changer sans redémarrer le
serveur. Pour laisser chaque utilisateur choisir son propre habillage sans
redémarrage, ce module génère du CSS injecté au runtime (via st.html) qui
recolore l'app par-dessus ce socle -- cf. THEMES ci-dessous pour ajouter une
palette.

Les couleurs de gain/perte (vert/rouge) restent volontairement proches d'un
thème à l'autre : elles gardent leur sens financier (hausse/baisse) plutôt
que de suivre l'esthétique choisie.
"""


THEMES = {
    "Violet Glow": {
        "description": "Le thème par défaut : glass violet sur noir, accents néon.",
        "bg": "#0A0812",
        "secondary_bg": "#161221",
        "text": "#F1EDFB",
        "border": "#2A2340",
        "primary": "#A78BFA",
        "accent_a": "#4DD4F0",
        "accent_b": "#C084FC",
        "accent_c": "#FF8A5B",
        "green": "#00E68A",
        "red": "#FF4D6D",
    },
    "Girly": {
        "description": "Rose profond et bordeaux sur fond prune quasi noir.",
        "bg": "#12060C",
        "secondary_bg": "#23101B",
        "text": "#FBEAF2",
        "border": "#3A1D2E",
        "primary": "#FF69B4",
        "accent_a": "#86A8CF",
        "accent_b": "#C38EB4",
        "accent_c": "#E8A0C4",
        "green": "#4ADE9A",
        "red": "#C2436D",
    },
    "Néon": {
        "description": "\"Toxic Pulse\" : vert fluo et violet électrique sur bleu nuit.",
        "bg": "#10131D",
        "secondary_bg": "#1D2331",
        "text": "#EAFBE0",
        "border": "#2A3345",
        "primary": "#8B53FE",
        "accent_a": "#00E5FF",
        "accent_b": "#8B53FE",
        "accent_c": "#FFB86B",
        "green": "#8EFF01",
        "red": "#FF3B5C",
    },
    "Dark Vibes": {
        "description": "\"Crimson Noir\" : rouge sang et bleu-gris sur noir absolu.",
        "bg": "#010003",
        "secondary_bg": "#1B0A10",
        "text": "#B9D3E2",
        "border": "#340A13",
        "primary": "#A4324B",
        "accent_a": "#4C6C81",
        "accent_b": "#87A4B5",
        "accent_c": "#25435D",
        "green": "#5FC79A",
        "red": "#7D0018",
    },
    "Océan": {
        "description": "Dégradé bleu profond vers bleu glacier.",
        "bg": "#020233",
        "secondary_bg": "#0B1450",
        "text": "#CAF0F8",
        "border": "#0B3D6E",
        "primary": "#00B4D8",
        "accent_a": "#0077B6",
        "accent_b": "#90E0EF",
        "accent_c": "#CAF0F8",
        "green": "#2DD4BF",
        "red": "#FF6B6B",
    },
    "Braise": {
        "description": "Teal électrique et rouge braise, contraste élevé.",
        "bg": "#0D1A2F",
        "secondary_bg": "#17364F",
        "text": "#E8F6F5",
        "border": "#411E3A",
        "primary": "#09D8C7",
        "accent_a": "#17364F",
        "accent_b": "#411E3A",
        "accent_c": "#BD0927",
        "green": "#2DD4A0",
        "red": "#BD0927",
    },
    "Crépuscule": {
        "description": "Pastel bleu nuit et rose poudré, tout en douceur.",
        "bg": "#0F1B2B",
        "secondary_bg": "#1B2E44",
        "text": "#F1E6ED",
        "border": "#26425A",
        "primary": "#C38EB4",
        "accent_a": "#86A8CF",
        "accent_b": "#C38EB4",
        "accent_c": "#E1CBD7",
        "green": "#7ED9A8",
        "red": "#E08FA0",
    },
    "Helios": {
        "description": "Mauve profond et rose poudré feutré, look dashboard finance.",
        "bg": "#120A11",
        "secondary_bg": "#221726",
        "text": "#F3EAF0",
        "border": "#3A2A38",
        "primary": "#C9A6C4",
        "accent_a": "#8B7091",
        "accent_b": "#D9A9CE",
        "accent_c": "#E8C4DC",
        "green": "#8FD9B6",
        "red": "#E08FA0",
    },
}


DEFAULT_THEME = "Violet Glow"


def theme_css(theme):
    """Construit le CSS qui applique `theme` par-dessus le thème statique.

    Cible les attributs data-testid de Streamlit (plus stables d'une version
    à l'autre que les classes générées) plutôt que d'introduire des
    variables CSS non documentées.
    """

    return f"""
<style>
.stApp {{
    background-color: {theme['bg']} !important;
    color: {theme['text']} !important;
}}

[data-testid="stHeader"] {{
    background-color: transparent !important;
}}

[data-testid="stSidebar"] {{
    background-color: {theme['bg']} !important;
    border-right: 1px solid {theme['border']} !important;
}}

[data-testid="stSidebar"] * {{
    color: {theme['text']} !important;
}}

h1, h2, h3, h4, h5, h6,
[data-testid="stHeading"] * {{
    color: {theme['text']} !important;
}}

a, a:visited {{
    color: {theme['primary']} !important;
}}

[data-testid="stBaseButton-primary"] {{
    background-color: {theme['primary']} !important;
    border-color: {theme['primary']} !important;
    color: {theme['bg']} !important;
}}

[data-testid="stBaseButton-secondary"] {{
    background-color: {theme['secondary_bg']} !important;
    border-color: {theme['border']} !important;
    color: {theme['text']} !important;
}}

[data-testid="stMetric"] {{
    background-color: {theme['secondary_bg']} !important;
    border-color: {theme['border']} !important;
}}

/* Mini-graphique (sparkline) des st.metric : Vega-Lite fixe son fond en
   inline SVG d'apres le theme statique -- on le realigne sur la carte. */
[data-testid="stMetricChart"] svg {{
    background-color: {theme['secondary_bg']} !important;
}}

[data-testid="stExpander"] summary,
[data-testid="stExpander"] details {{
    background-color: {theme['secondary_bg']} !important;
    border-color: {theme['border']} !important;
    color: {theme['text']} !important;
}}

[data-testid="stDataFrame"] {{
    border-color: {theme['border']} !important;
}}

[data-testid="stSelectbox"] div[role="group"],
[data-testid="stTextInputRootElement"],
[data-testid="stNumberInputContainer"] {{
    background-color: {theme['secondary_bg']} !important;
    border-color: {theme['border']} !important;
}}

[data-testid="stTextInputField"],
[data-testid="stNumberInputField"],
[data-testid="stSelectbox"] input {{
    background-color: transparent !important;
    color: {theme['text']} !important;
}}

[data-testid="stSlider"] div[style*="position: absolute"] {{
    background-color: {theme['primary']} !important;
}}

[data-testid="stButtonGroup"] button[data-selected="true"] {{
    background-color: {theme['primary']} !important;
    border-color: {theme['primary']} !important;
    color: {theme['bg']} !important;
}}

[data-testid="stContainer"] {{
    border-color: {theme['border']} !important;
}}

/* Menu de gauche (st.page_link) : la page active est rendue "disabled"
   (on ne se clique pas soi-meme) -- on la transforme en pastille pleine
   plutot que de la laisser grisee, pour qu'elle se voie comme selectionnee
   et non comme indisponible. */
[data-testid="stPageLink-NavLink"] {{
    border-radius: 999px !important;
}}

[data-testid="stPageLink-NavLink"][disabled] {{
    background-color: {theme['primary']} !important;
    opacity: 1 !important;
}}

[data-testid="stPageLink-NavLink"][disabled] * {{
    color: {theme['bg']} !important;
    opacity: 1 !important;
}}
</style>
"""


def theme_swatch_html(theme):
    """Bande d'aperçu (petits carrés de couleur) pour la palette choisie."""

    swatches = [
        theme["primary"],
        theme["accent_a"],
        theme["accent_b"],
        theme["accent_c"],
        theme["green"],
        theme["red"],
    ]

    chips = "".join(
        f'<span style="display:inline-block;width:20px;height:20px;'
        f'border-radius:5px;margin-right:4px;background:{color};'
        f'border:1px solid rgba(255,255,255,0.15);"></span>'
        for color in swatches
    )

    return f'<div style="margin:4px 0 12px 0;">{chips}</div>'
