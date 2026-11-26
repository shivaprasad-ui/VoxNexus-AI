import re
def interpret(text):
    text=text.lower()
    if re.search(r'\b(balance|statement)\b',text): return {'action':'check_balance','message':'Request a protected balance check.'}
    if re.search(r'\b(transfer|send money|pay)\b',text): return {'action':'transfer_money','message':'Enter amount and recipient in the transaction panel. Independent approval required.'}
    return {'action':None,'message':'I can help with mock balance checks and transfers.'}
