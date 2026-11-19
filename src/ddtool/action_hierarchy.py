from dataclasses import replace


def builtin_group(key: str) -> str:
    if any(word in key for word in ("config", "dns", "netstat", "ncpa", "network", "hosts")):
        return "网络与诊断"
    if key in {"preset-keep-awake", "preset-postpone-lock"}:
        return "电源与锁屏"
    return "系统与终端"


class ActionHierarchy:
    def __init__(self, actions, groups=(), order=()):
        self.actions = {f"a:{action.id}": action for action in actions}
        self.children = {"": []}
        for path in [*groups, *(action.menu_path for action in actions)]:
            self.add_path(path)
        for key, action in self.actions.items():
            self.children[self.group_key(action.menu_path)].append(key)
        ranks = {key: index for index, key in enumerate(order)}
        for siblings in self.children.values():
            siblings.sort(key=lambda key: ranks.get(key, len(ranks)))

    @staticmethod
    def group_key(path):
        return f"g:{path}" if path else ""

    def add_path(self, path):
        parent = ""
        prefix = []
        for name in path.split("/") if path else ():
            prefix.append(name)
            key = self.group_key("/".join(prefix))
            if key not in self.children:
                self.children[parent].append(key)
                self.children[key] = []
            parent = key
        return parent

    def parent(self, key):
        if key in self.actions:
            return self.group_key(self.actions[key].menu_path)
        return self.group_key(key[2:].rpartition("/")[0])

    def walk(self, parent="", depth=0):
        for key in self.children[parent]:
            yield key, parent, depth
            if key in self.children:
                yield from self.walk(key, depth + 1)

    def create(self, parent, name):
        path = self.destination(parent, name)
        return self.add_path(path)

    def destination(self, parent, name, current=""):
        if (parent not in self.children or not 1 <= len(name) <= 64 or not name.isprintable()
                or any(char in name for char in "/\\") or name in {"退出", "工具设置", "快捷操作"}):
            raise ValueError("请输入有效的分组名称，不可包含斜线或使用保留名称。")
        path = f"{parent[2:]}/{name}" if parent else name
        key = self.group_key(path)
        if key != current and key in self.children:
            raise ValueError("同级已有同名分组。")
        return path

    def rename(self, key, name):
        parent = self.parent(key)
        path = self.destination(parent, name, key)
        new_key = self._relocate(key, parent, path)
        siblings = self.children[parent]
        siblings[siblings.index(key)] = new_key
        return new_key

    def remove(self, key):
        if self.children[key]:
            raise ValueError("请先移出分组中的操作和子分组。")
        self.children[self.parent(key)].remove(key)
        del self.children[key]

    def _relocate(self, key, parent, new_path=None):
        if key in self.actions:
            self.actions[key] = replace(self.actions[key], menu_path=parent[2:])
            return key
        path = new_path if new_path is not None else self.destination(parent, key[2:].rsplit("/", 1)[-1], key)
        new_key = self.group_key(path)
        if new_key != key:
            descendants = self.children.pop(key)
            self.children[new_key] = []
            for child in descendants:
                child_path = f"{path}/{child[2:].rsplit('/', 1)[-1]}" if child in self.children else None
                self.children[new_key].append(self._relocate(child, new_key, child_path))
        return new_key

    def move(self, key, target, placement):
        if key == target or key not in self.actions and key not in self.children or not key:
            return key
        old_parent = self.parent(key)
        if placement == "inside" and target in self.children:
            parent = target
        elif placement in {"before", "after"} and (target in self.actions or target and target in self.children):
            parent = self.parent(target)
        else:
            raise ValueError("请选择自定义分组或操作作为放置位置。")
        if key in self.children and (parent == key or parent.startswith(key + "/")):
            raise ValueError("不能将分组移入自己的子分组。")
        new_key = self._relocate(key, parent)
        self.children[old_parent].remove(key)
        siblings = self.children[parent]
        index = len(siblings) if placement == "inside" else siblings.index(target) + (placement == "after")
        siblings.insert(index, new_key)
        return new_key
