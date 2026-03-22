def calculate_balances(expenses, splits):
    """
    Calculate who paid how much and who owes whom.
    Returns: dict of {user_id: {name, paid, share, balance}}
    """
    paid = {}      # how much each person paid
    owed = {}      # how much each person owes
    names = {}     # user names

    # Calculate total paid per person
    for exp in expenses:
        exp_id, paid_by, shared_amount, created_at, first_name = exp
        names[paid_by] = first_name
        paid[paid_by] = paid.get(paid_by, 0) + float(shared_amount)

    # Calculate fair share per person
    for split in splits:
        exp_id, user_id, amount, first_name = split
        names[user_id] = first_name
        owed[user_id] = owed.get(user_id, 0) + float(amount)

    # Calculate balances
    all_users = set(list(paid.keys()) + list(owed.keys()))
    balances = {}
    for user_id in all_users:
        total_paid = paid.get(user_id, 0)
        fair_share = owed.get(user_id, 0)
        balance = total_paid - fair_share
        balances[user_id] = {
            'name': names.get(user_id, 'Unknown'),
            'paid': total_paid,
            'share': fair_share,
            'balance': balance
        }

    return balances


def calculate_settlements(balances):
    """
    Calculate minimum transactions to settle all debts.
    Returns list of (debtor, creditor, amount)
    """
    debtors = []
    creditors = []

    for user_id, data in balances.items():
        if data['balance'] < -0.01:
            debtors.append([user_id, data['name'], abs(data['balance'])])
        elif data['balance'] > 0.01:
            creditors.append([user_id, data['name'], data['balance']])

    settlements = []
    i, j = 0, 0

    while i < len(debtors) and j < len(creditors):
        debtor = debtors[i]
        creditor = creditors[j]
        amount = min(debtor[2], creditor[2])

        settlements.append({
            'from_id': debtor[0],
            'from_name': debtor[1],
            'to_id': creditor[0],
            'to_name': creditor[1],
            'amount': round(amount, 2)
        })

        debtor[2] -= amount
        creditor[2] -= amount

        if debtor[2] < 0.01:
            i += 1
        if creditor[2] < 0.01:
            j += 1

    return settlements