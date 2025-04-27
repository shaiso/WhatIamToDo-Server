PASTEL_COLORS = [
    "#FFB3BA",  # розоватый
    "#FFDFBA",  # персиковый
    "#FFFFBA",  # пастельно-желтый
    "#BFFCC6",  # пастельно-зелёный
    "#BFDFFC",  # голубоватый
    "#B28DFF",  # сиреневый
    "#FFDB8B",
    "#FF7514",
    "#FF9BAA",
    "#3EB489",
    "#AFDAFC",
    "#CCCCFF",
    "#393e46",
    "#d72323",
    "#10ddc2"

]

def get_unique_pastel_color(used_colors):
    """
    Возвращает цвет из PASTEL_COLORS, который не содержится в used_colors.
    """
    for c in PASTEL_COLORS:
        if c not in used_colors:
            return c
    return None
