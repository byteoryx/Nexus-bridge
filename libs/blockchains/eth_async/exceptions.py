class GasException(Exception):
    pass

class InsufficientFundsException(Exception):
    pass

class NonceException(Exception):
    pass

class TransactionException(Exception):
    pass

class AmountExceedsBalanceException(Exception):
    pass

class TxFailed(Exception):
    pass
