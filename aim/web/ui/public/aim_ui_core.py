####################
# Bindings for fetching Aim Objects
####################

from pyodide.ffi import create_proxy
from js import search
import hashlib


memoize_cache = {}


def deep_copy(obj):
    if isinstance(obj, (list, tuple)):
        return type(obj)(deep_copy(x) for x in obj)
    elif isinstance(obj, dict):
        return type(obj)((deep_copy(k), deep_copy(v)) for k, v in obj.items())
    elif isinstance(obj, set):
        return type(obj)(deep_copy(x) for x in obj)
    elif hasattr(obj, '__dict__'):
        result = type(obj)()
        result.__dict__.update(deep_copy(obj.__dict__))
        return result
    elif isinstance(obj, memoryview):
        return memoryview(bytes(obj))
    else:
        return obj


def memoize_async(func):
    async def wrapper(*args, **kwargs):
        if func.__name__ not in memoize_cache:
            memoize_cache[func.__name__] = {}

        key = generate_key(args + tuple(kwargs.items()))

        if key not in memoize_cache[func.__name__]:
            memoize_cache[func.__name__][key] = await func(*args, **kwargs)

        return memoize_cache[func.__name__][key]

    return wrapper


def memoize(func):
    def wrapper(*args, **kwargs):
        if func.__name__ not in memoize_cache:
            memoize_cache[func.__name__] = {}

        key = generate_key(args + tuple(kwargs.items()))

        if key not in memoize_cache[func.__name__]:
            memoize_cache[func.__name__][key] = func(*args, **kwargs)

        return memoize_cache[func.__name__][key]

    return wrapper


class Object:
    def __init__(self, type, methods={}):
        self.type = type
        self.methods = methods
        self.items = []

    # @memoize_async
    async def query(self, query=""):
        data = await search(self.type, query)
        data = create_proxy(data.to_py())
        items = []
        i = 0
        for item in data:
            d = item
            d["type"] = self.type
            d["key"] = i
            i = i + 1
            items.append(d)
        self.items = items
        data.destroy()
        return items


class MetricObject(Object):
    def dataframe(self, key):
        import pandas as pd

        metric = self.items[key]

        df_source = {
            "run.hash": [],
            "metric.name": [],
            "metric.context": [],
            "step": [],
            "value": [],
        }

        for i, s in enumerate(metric["steps"]):
            df_source["run.hash"].append(metric["run"]["hash"])
            df_source["metric.name"].append(metric["name"])
            df_source["metric.context"].append(str(metric["context"]))
            df_source["step"].append(metric["steps"][i])
            df_source["value"].append(metric["values"][i])

        return pd.DataFrame(df_source)


Metric = MetricObject("metric")
Images = Object("images")
Figures = Object("figures")
Audios = Object("audios")
Texts = Object("texts")
Distributions = Object("distributions")


####################
# Bindings for visualizing data with data viz elements
####################


def find(obj, element):
    keys = element.split(".")
    rv = obj
    for key in keys:
        try:
            rv = rv[key]
        except:
            return None
    return rv


colors = [
    "#3E72E7",
    "#18AB6D",
    "#7A4CE0",
    "#E149A0",
    "#E43D3D",
    "#E8853D",
    "#0394B4",
    "#729B1B",
]

stroke_styles = [
    "none",
    "5 5",
    "10 5 5 5",
    "10 5 5 5 5 5",
    "10 5 5 5 5 5 5 5",
    "20 5 10 5",
    "20 5 10 5 10 5",
    "20 5 10 5 10 5 5 5",
    "20 5 10 5 5 5 5 5",
]


def generate_key(data):
    content = str(data)
    return hashlib.md5(content.encode()).hexdigest()


viz_map_keys = {}


def update_viz_map(viz_type, key=None):
    if key != None:
        viz_map_keys[key] = key
        return key
    if viz_type in viz_map_keys:
        viz_map_keys[viz_type] = viz_map_keys[viz_type] + 1
    else:
        viz_map_keys[viz_type] = 0

    viz_key = viz_type + str(viz_map_keys[viz_type])

    return viz_key


def apply_group_value_pattern(value, list):
    if type(value) is int:
        return list[value % len(list)]
    return value


@memoize
def group(name, data, options, key=None):
    group_map = {}
    grouped_data = []
    items = deep_copy(data)
    for item in items:
        group_values = []
        if callable(options):
            val = options(item)
            if type(val) == bool:
                val = int(val)
            group_values.append(val)
        else:
            for opt in options:
                val = find(
                    item,
                    str(opt) if type(opt) is not str else opt.replace("metric.", ""),
                )
                group_values.append(val)

        group_key = generate_key(group_values)

        if group_key not in group_map:
            group_map[group_key] = {
                "options": options,
                "val": group_values,
                "order": None,
            }
        item[name] = group_key
        grouped_data.append(item)
    sorted_groups = group_map
    if callable(options):
        sorted_groups = {
            k: v
            for k, v in sorted(
                sorted_groups.items(), key=lambda x: str(x[1]["val"]), reverse=True
            )
        }
    else:
        for i, opt in enumerate(options):
            sorted_groups = {
                k: v
                for k, v in sorted(
                    sorted_groups.items(),
                    key=lambda x: (3, str(x[1]["val"][i]))
                    if type(x[1]["val"][i]) in [tuple, list, dict]
                    else (
                        (0, int(x[1]["val"][i]))
                        if str(x[1]["val"][i]).isdigit()
                        else (
                            (2, str(x[1]["val"][i]))
                            if x[1]["val"][i] is None
                            else (1, str(x[1]["val"][i]))
                        )
                    ),
                )
            }

    i = 0
    for group_key in sorted_groups:
        sorted_groups[group_key]["order"] = (
            sorted_groups[group_key]["val"][0] if callable(options) else i
        )
        i = i + 1
    return sorted_groups, grouped_data


current_layout = []


state = {}


def set_state(update):
    from js import setState

    state.update(update)
    setState(update)


block_context = {
    "current": 0,
}


def render_to_layout(data):
    from js import updateLayout

    is_found = False
    for i, cell in enumerate(current_layout):
        if cell["key"] == data["key"]:
            current_layout[i] = data
            is_found = True

    if is_found == False:
        current_layout.append(data)

    updateLayout(current_layout)


class Element:
    def __init__(self):
        self.parent_block = None

    def set_parent_block(self, block):
        self.parent_block = block


class Block(Element):
    def __init__(self, type):
        super().__init__()
        block_context["current"] += 1
        self.block_context = {
            "id": block_context["current"],
            "type": type
        }
        self.key = generate_key(self.block_context)

        self.render()

    def add(self, element):
        element.set_parent_block(self.block_context)
        element.render()

    def render(self):
        block_data = {
            "element": 'block',
            "block_context": self.block_context,
            "key": self.key,
            "parent_block": self.parent_block
        }

        render_to_layout(block_data)


class Row(Block):
    def __init__(self):
        super().__init__('row')


class Column(Block):
    def __init__(self):
        super().__init__('column')


class Component(Element):
    def __init__(self, key, type):
        super().__init__()
        self.state = {}
        self.key = key
        self.type = type
        self.data = None
        self.callbacks = {}
        self.options = {}
        self.state = state[key] if key in state else {}
        self.no_facet = True

    def set_state(self, value):
        self.state.update(value)
        set_state({
            self.key: value
        })

    def render(self):
        component_data = {
            "type": self.type,
            "key": self.key,
            "data": self.data,
            "callbacks": self.callbacks,
            "options": self.options,
            "parent_block": self.parent_block,
            "no_facet": self.no_facet
        }

        component_data.update(self.state)

        render_to_layout(component_data)

    def group(self, prop, value=[]):
        group_map, group_data = group(prop, self.data, value, self.key)

        items = []
        for i, item in enumerate(self.data):
            elem = dict(item)
            current = group_map[group_data[i][prop]]

            if prop == "color":
                color_val = apply_group_value_pattern(
                    current["order"], colors
                )
                elem["color"] = color_val
                elem["color_val"] = current["val"]
                elem["color_options"] = value
            elif prop == "stroke_style":
                stroke_val = apply_group_value_pattern(
                    current["order"], stroke_styles
                )
                elem["dasharray"] = stroke_val
                elem["dasharray_val"] = current["val"]
                elem["dasharray_options"] = value
            else:
                elem[prop] = current["order"]
                elem[f"{prop}_val"] = current["val"]
                elem[f"{prop}_options"] = value

            if prop == "row" or prop == "column":
                self.no_facet = False

            items.append(elem)

        self.data = items

        self.render()


class LineChart(Component):
    def __init__(self, data, x, y, color=[], stroke_style=[], options={}, key=None):
        component_type = "LineChart"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        color_map, color_data = group("color", data, color, component_key)
        stroke_map, stroke_data = group("stroke_style", data, stroke_style, component_key)
        lines = []
        for i, item in enumerate(data):
            color_val = apply_group_value_pattern(
                color_map[color_data[i]["color"]]["order"], colors
            )
            stroke_val = apply_group_value_pattern(
                stroke_map[stroke_data[i]["stroke_style"]]["order"], stroke_styles
            )

            line = dict(item)
            line["key"] = i
            line["data"] = {"xValues": find(item, x), "yValues": find(item, y)}
            line["color"] = color_val
            line["dasharray"] = stroke_val

            lines.append(line)

        self.data = lines
        self.options = options
        self.callbacks = {
            "on_active_point_change": self.on_active_point_change
        }

        self.render()

    @property
    def active_line(self):
        return self.state["active_line"] if "active_line" in self.state else None

    @property
    def focused_line(self):
        return self.state["focused_line"] if "focused_line" in self.state else None

    @property
    def active_point(self):
        return self.state["active_point"] if "active_point" in self.state else None

    @property
    def focused_point(self):
        return self.state["focused_point"] if "focused_point" in self.state else None

    async def on_active_point_change(self, val, is_active):
        data = create_proxy(val.to_py())
        point = dict(data)
        data.destroy()
        item = self.data[point["key"]]
        if is_active:
            self.set_state({
                "focused_line": item,
                "focused_point": point,
            })
        else:
            self.set_state({
                "active_line": item,
                "active_point": point,
            })


class ImagesList(Component):
    def __init__(self, data, key=None):
        component_type = "Images"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        images = []

        for i, item in enumerate(data):
            image = item
            image["key"] = i

            images.append(image)

        self.data = images

        self.render()


class AudiosList(Component):
    def __init__(self, data, key=None):
        component_type = "Audios"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        audios = []

        for i, item in enumerate(data):
            audio = item
            audio["key"] = i

            audios.append(audio)

        self.data = audios

        self.render()


class TextsList(Component):
    def __init__(self, data, color=[], key=None):
        component_type = "Text"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        color_map, color_data = group("color", data, color, component_key)

        texts = []

        for i, item in enumerate(data):
            color_val = apply_group_value_pattern(
                color_map[color_data[i]["color"]]["order"], colors
            )
            text = item
            text["key"] = i
            text["color"] = color_val

            texts.append(text)

        self.data = texts

        self.render()


class FiguresList(Component):
    def __init__(self, data, key=None):
        component_type = "Figures"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        figures = []

        for i, item in enumerate(data):
            figure = {
                "key": i,
                "data": item.to_json(),
            }

            figures.append(figure)

        self.data = figures

        self.render()


class JSON(Component):
    def __init__(self, data, key=None):
        component_type = "JSON"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        self.data = data

        self.render()


class Table(Component):
    def __init__(self, data, key=None):
        component_type = "DataFrame"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        self.data = data.to_json(orient="records")

        self.render()


class HTML(Component):
    def __init__(self, data, key=None):
        component_type = "HTML"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        self.data = data

        self.render()


class RunMessages(Component):
    def __init__(self, run_hash, key=None):
        component_type = "RunMessages"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        self.data = run_hash

        self.render()


class Plotly(Component):
    def __init__(self, fig, key=None):
        component_type = "Plotly"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        self.data = fig.to_json()

        self.render()


class Union(Component):
    def __init__(self, components, key=None):
        component_type = "Union"
        component_key = update_viz_map(component_type, key)
        super().__init__(component_key, component_type)

        for i, elem in reversed(list(enumerate(current_layout))):
            for comp in components:
                if elem["key"] == comp.key:
                    del current_layout[i]

        self.data = []
        for comp in components:
            self.data = self.data + comp.data
            self.callbacks.update(comp.callbacks)

        def get_viz_for_type(type):
            for comp in components:
                if comp.data and comp.data[0] and comp.data[0]["type"] == type:
                    return comp.type

        self.type = get_viz_for_type

        self.render()
