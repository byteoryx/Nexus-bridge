from decimal import Decimal


class TokenAmount:
    Wei: int
    Ether: Decimal
    decimals: int

    def __init__(self, amount: int | float | str | Decimal, decimals: int, wei: bool = False) -> None:
        if wei:
            self.Wei: int = int(amount)
            self.Ether: Decimal = Decimal(str(amount)) / 10 ** decimals

        else:
            self.Wei: int = int(Decimal(str(amount)) * 10 ** decimals)
            self.Ether: Decimal = Decimal(str(amount))

        self.decimals = decimals

    def __str__(self):
        rounding = int(self.decimals / 3)
        return f'{round(self.Ether, rounding)}'

    def __repr__(self):
        rounding = int(self.decimals / 3)
        return f'{round(self.Ether, rounding)}'

    def __int__(self):
        return int(self.Wei)

    def __eq__(self, other):
        return self.Wei == other.Wei

    def __lt__(self, other):
        # self < other
        return self.Wei < other.Wei

    def __gt__(self, other):
        # self > other
        return self.Wei > other.Wei

    def __le__(self, other):
        # self <= other
        return self.Wei <= other.Wei

    def __ge__(self, other):
        # self >= other
        return self.Wei >= other.Wei
