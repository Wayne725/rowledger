from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Columns:
    key: str = "order_id"
    amount: str = "amount"
    currency: str = "currency"
    sheet: str | None = None

    def __post_init__(self):
        names = [self.key, self.amount, self.currency]
        if any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError("Column names must be nonempty strings.")
        if len(set(names)) != 3:
            raise ValueError("Key, amount and currency must use different columns.")
        if self.sheet is not None and (not isinstance(self.sheet, str) or not self.sheet):
            raise ValueError("Sheet must be a nonempty string or null.")


@dataclass(frozen=True)
class Rules:
    orders: Columns = field(default_factory=Columns)
    payments: Columns = field(default_factory=Columns)
    minor_units: dict[str, int] = field(default_factory=lambda: {"USD": 2, "EUR": 2, "TWD": 0, "JPY": 0})
    trim_keys: bool = True

    def __post_init__(self):
        if not isinstance(self.minor_units, dict) or not self.minor_units:
            raise ValueError("minor_units must be a nonempty currency-to-scale mapping.")
        for currency, scale in self.minor_units.items():
            if (not isinstance(currency, str) or len(currency) != 3
                    or not currency.isascii() or not currency.isalpha() or not currency.isupper()
                    or type(scale) is not int or not 0 <= scale <= 6):
                raise ValueError("Currency codes must be three uppercase letters; scales must be integers 0–6.")
        if type(self.trim_keys) is not bool:
            raise ValueError("trim_keys must be true or false.")

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) - {"orders", "payments", "minor_units", "trim_keys"}:
            raise ValueError("Unknown or invalid rules fields.")
        values = dict(data)
        for side in ("orders", "payments"):
            if side in values:
                mapping = values[side]
                if not isinstance(mapping, dict) or set(mapping) - {"key", "amount", "currency", "sheet"}:
                    raise ValueError(f"Invalid {side} column mapping.")
                values[side] = Columns(**mapping)
        return cls(**values)

    def to_dict(self):
        return asdict(self)
