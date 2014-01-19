"""
bitcointip.py - Willie BitcoinTip Module
Copyright 2013, Tyler Crumpton
Licensed under the GPLv3.

http://tylercrumpton.com
"""

import random
import hashlib
import json
import urllib2

import time
from datetime import datetime

from willie import web

SATOSHI = 100000000 # number of satoshis per bitcoin

def setup(willie):
    if not willie.db.check_table('tipaccounts', ('nick','balance','authed','verified','password_hash','salt','w_addr','d_addr','last_deposit'), 'nick'):
        willie.db.add_table('tipaccounts', ('nick','balance','authed','verified','password_hash','salt','w_addr','d_addr','last_deposit'), 'nick')
        
    if not willie.db.tipaccounts.contains(willie.nick):
        willie.db.tipaccounts.update(willie.nick, {'balance':'0','authed':'no','verified':'yes','password_hash':'','salt':'','w_addr':'','d_addr':'','last_deposit':''})
    
    # Deauth all users on connect
    while willie.db.tipaccounts.contains('yes','authed'):
        nick = willie.db.tipaccounts.get('yes','nick','authed')
        willie.db.tipaccounts.update(nick, {'authed':'no'})
        willie.debug("DEAUTH", "Nick {} was deauthed.".format(nick), 'always')

        
def help(willie, trigger):
    text = trigger.group().split()
    if not isPrivMsg(trigger) and len(text) == 1:
        willie.say("Use '/msg BitcoinTip !help' for info on using the BitcoinTip bot.")
    else:
        if len(text) == 1:
            # General help text:
            willie.say("Available commands: (#)help, signup, btc-realtime, (#)auth, (@#)deauth, (@#)accept, (@)tip, (@#)balance, (@)btcflip")
            willie.say("Legend: @ - Requires authentication | # - Requires private message")
            willie.say("Use '!help <commandname>' to get more detailed help about a particular command.")
        else:
            # Specific help text:
            command = text[1].lower()
            if command == 'help':
                willie.say('Description: Displays a list of available commands and provides more detailed info on specific commands.')
                willie.say('Usage: !help signup')
                willie.say('Aliases: !btchelp, !btc-help, !helpbtc, !help-btc')
            elif command == 'signup':
                willie.say('Description: Creates an account with the BitcoinTip bot. You must be registered with NickServ for this to work.')
                willie.say('Usage: !signup')
                willie.say('Aliases: !register, !signmeup')
            elif command == 'btc-realtime':
                willie.say('Description: Displays the last BTC trade price on Bitstamp.')
                willie.say('Usage: !btc-realtime')
                willie.say('Aliases: !btc-rt')
            elif command == 'auth':
                willie.say('Description: Tells the BitcoinTip bot to send you an authentication challenge via MemoServ. Private message only.')
                willie.say('Usage: !auth')
                willie.say('Aliases: !authenticate')
            elif command == 'deauth':
                willie.say('Description: Forces the BitcoinTip bot to deauthenticate you immediately. Requires auth. Private message only.')
                willie.say('Usage: !deauth')
                willie.say('Aliases: !deauthenticate, !unauth')
            elif command == 'accept':
                willie.say('Description: Accept any incoming pending Bitcoin tips. Requires auth. Private message only.')
                willie.say('Usage: !accept')
                willie.say('Aliases: !btc-accept, !accept-btc, !acceptbtc, !btcaccept')
            elif command == 'tip':
                willie.say('Description: Sends an amount of Bitcoin to the given nick. Requires auth.')
                willie.say('Usage: !tip tylercrumpton 1.0 BTC')
                willie.say('Aliases: !btc-tip, !tip-btc, !tipbtc, !btctip')
            elif command == 'balance':
                willie.say('Description: Displays your current and pending balances. Requires auth. Private message only.')
                willie.say('Usage: !balance')
                willie.say('Aliases: !btc-balance, !btcbalance, !balance-btc, !balancebtc')
            elif command == 'btcflip':
                willie.say("Description: Flips a coin; if it's heads you win the amount you bet, if it's tails you lose the amount. Requires auth.")
                willie.say('Usage: !btcflip 0.01 BTC')
                willie.say('Aliases: !btc-flip, !flipbtc, !flip-btc')
help.commands = ['help', 'btchelp', 'btc-help', 'helpbtc', 'help-btc']
help.priority = 'medium'
help.example = '!help <command>'

def directHelp(willie, trigger):
    # General help text:
    willie.say("Available commands: (#)help, signup, btc-realtime, (#)auth, (@#)deauth, (@#)accept, (@)tip, (@#)balance, (@)btcflip")
    willie.say("Legend: @ - Requires authentication | # - Requires private message")
    willie.say("Use '!help <commandname>' to get more detailed help about a particular command.")
directHelp.rule = ('$nick', r'(?i)h[a|e]lp(?:[?!]+)?$')
directHelp.priority = 'medium'

def tip(willie, trigger):
    text = trigger.group().split()
    if len(text) != 3 and len(text) != 4:
        willie.say('Wrong number of arguments.')
    else:
        if len(text) == 3:
            command,toNick,amount = text
            unit = 'BTC'
        else:
            command,toNick,amount,unit = text
        toNick = toNick.lower()
        fromNick = trigger.nick.lower()
        if fromNick == toNick:
            willie.say("You can't send tips to yourself.")
            return
        try:
            intSatoshis = convertToSatoshis(willie, amount, unit)
            if intSatoshis != "ERROR":
                floatBitcoins = float(intSatoshis) / SATOSHI
                stringBitcoins = "{:.8f}".format(floatBitcoins).rstrip("0")
                valid = True
            else:
                valid = False
        except ValueError:
            willie.say("Amount entered is not a number.")
            valid = False
        if valid and sendPayment(willie, fromNick, toNick, intSatoshis, True):
            willie.say("{} BTC has been sent to {}.".format(stringBitcoins, toNick)) 
tip.commands = ['btctip', 'tip', 'tipbtc', 'tip-btc', 'btc-tip']
tip.priority = 'medium'
tip.example = '!btctip $nick <amount> [BTC|USD]'

def signup(willie, trigger):
    nick = trigger.nick.lower()
    if willie.db.tipaccounts.contains(nick):
        willie.say('You are already registered with me!')
    else:
        # Open the file and read the addresses:
        with open("/home/tyler/.willie/bitcointip_files/addrs", "r") as f:
            lines = f.readlines()
        # Read the first address
        depositAddr = lines[0]
        # Remove any newlines from the address:
        depositAddr = depositAddr.rstrip()
        if depositAddr != "":
            # Delete that address from the list
            del lines[0]
            # Open the file so we can save the other address back to the file:
            with open("/home/tyler/.willie/bitcointip_files/addrs", "w") as f:
                for line in lines:
                    f.write(line)
        willie.db.tipaccounts.update(nick, {'balance':'0','password_hash':'','authed':'no','verified':'no','salt':'','d_addr':depositAddr})
        willie.msg(nick, 'Welcome to BitcoinTip! To finish creating your account, please choose a password using the "!setpass" command in this private message. (e.g. "!setpass PaSSW0Rd")')
signup.commands = ['signup', 'register', 'signmeup']
signup.priority = 'medium'
signup.example = '!signup'

def verify(willie, trigger):
    # Check to see if the admin is using the command, ignore everyone else:
    nick = trigger.nick.lower()
    if nick == "tylercrumpton" and getAuthStatus(willie, nick) == "authed":
        text = trigger.group().split()
        if len(text) == 2:
            command, nick = text
            nick = nick.lower()
            if willie.db.tipaccounts.contains(nick):
                if willie.db.tipaccounts.get(nick, 'verified') != 'yes':
                    willie.db.tipaccounts.update(nick, {'verified':'yes'})
                    willie.say("{} has been verified with me. They may now recieve tips!".format(nick))
                else:
                    willie.say("{} has already been verified with me.".format(nick))
            else:
                willie.say("{} doesn't have an account with me.".format(nick))
        else:
            willie.say("Incorrect number of arguments.")
verify.commands = ["verify"]

def deposit(willie, trigger):
    nick = trigger.nick.lower()
    # PrivMsg-only command:
    if isPrivMsg(trigger):
        # Auth-only command:
        authStatus = getAuthStatus(willie, nick)
        if authStatus == "authed":
            addr = willie.db.tipaccounts.get(nick, 'd_addr')
            if addr != None:
                willie.say("Your deposit address is: {}. Send an amount of Bitcoin to this address to deposit into your BitcoinTip account.".format(addr))
            else:
                willie.say("You do not currently have a deposit address. This is a failing on the bot owner's part, not your own. Poke them to get a deposit address.")
        elif authStatus == "deauthed":
            willie.say('You are not authenticated. You must first authenticate with "/msg BitcoinTip !auth".')
        elif authStatus == "unregistered":
            willie.say('The user account for {} has not yet been set up. Set up a BitcoinTip account with "!signup"'.format(nick))
deposit.commands = ['deposit', 'btcdeposit', 'depositbtc']
deposit.priority = 'medium'

def btcrealtime(willie, trigger):
    text = trigger.group().split()
    numOfUnit = 1
    valid = True
    if len(text) >= 2:
        try:
            numOfUnit = float(text[1])
        except ValueError:
            willie.say("Amount entered is not a number.")
            valid = False
    if valid:
        try:
            data = web.get("https://www.bitstamp.net/api/ticker/", 10)
            decoded = json.loads(data)
            timeSince = int(round(time.time() - float(decoded["timestamp"])))
            totalConverted = float(decoded["last"]) * float(numOfUnit)
            willie.say("{} BTC @ Bitstamp is currently {} USD. ({:d} seconds ago)".format(numOfUnit, totalConverted , timeSince))
        except KeyError:
            willie.say("There was an error in retrieving realtime data from Bitstamp.")
        except:
            willie.say("There was an error in retrieving realtime data from Bitstamp.")
btcrealtime.commands = ['btc-rt', 'btc-realtime']
btcrealtime.priority = 'medium'

def btcbuy(willie, trigger):
    text = trigger.group().split()
    num = 1
    valid = True
    if len(text) >= 2:
        try:
            num = float(text[1])
        except ValueError:
            willie.say("Amount entered is not a number.")
            valid = False
    if valid:
        try:
            data = web.get("https://coinbase.com/api/v1/prices/buy?qty={}".format(num), 10)
            decoded = json.loads(data)
            subtotal = decoded["subtotal"]["amount"]
            fees = float(decoded["fees"][0]["coinbase"]["amount"]) + float(decoded["fees"][1]["bank"]["amount"])
            total = decoded["total"]["amount"]
            willie.say("You can buy {} BTC at Coinbase for ${} + ${} in fees (${} total).".format(num, subtotal, fees , total))
        except KeyError:
            willie.say("There was an error in retrieving realtime data from Coinbase.")
        except:
            willie.say("There was an error in retrieving realtime data from Coinbase.")
btcbuy.commands = ['btcbuy', 'btc-buy']
btcbuy.priority = 'medium'

def btcsell(willie, trigger):
    text = trigger.group().split()
    num = 1
    valid = True
    if len(text) >= 2:
        try:
            num = float(text[1])
        except ValueError:
            willie.say("Amount entered is not a number.")
            valid = False
    if valid:
        try:
            data = web.get("https://coinbase.com/api/v1/prices/sell?qty={}".format(num), 10)
            decoded = json.loads(data)
            subtotal = decoded["subtotal"]["amount"]
            fees = float(decoded["fees"][0]["coinbase"]["amount"]) + float(decoded["fees"][1]["bank"]["amount"])
            total = decoded["total"]["amount"]
            willie.say("You can sell {} BTC at Coinbase for ${} - ${} in fees (${} total).".format(num, subtotal, fees , total))
        except KeyError:
            willie.say("There was an error in retrieving realtime data from Coinbase.")
        except:
            willie.say("There was an error in retrieving realtime data from Coinbase.")
btcsell.commands = ['btcsell', 'btc-sell']
btcsell.priority = 'medium'

def ltcrealtime(willie, trigger):
    text = trigger.group().split()
    numOfUnit = 1
    valid = True
    if len(text) >= 2:
        try:
            numOfUnit = float(text[1])
        except ValueError:
            willie.say("Amount entered is not a number.")
            valid = False
    if valid:
        try:
            data = web.get("https://btc-e.com/api/2/ltc_usd/ticker", 10)
            decoded = json.loads(data)
            serverTime = int(decoded["ticker"]["server_time"])
            updateTime = int(decoded["ticker"]["updated"])
            timeSince = serverTime - updateTime
            totalConverted = float(decoded["ticker"]["last"]) * float(numOfUnit)
            willie.say("{} LTC @ BTC-e is currently {} USD. ({:d} seconds ago)".format(numOfUnit, totalConverted , timeSince))
        except KeyError:
            willie.say("There was an error in retrieving realtime data from BTC-e.")
        except:
            willie.say("There was an error in retrieving realtime data from BTC-e.")
ltcrealtime.commands = ['ltc-rt', 'ltc-realtime']
ltcrealtime.priority = 'medium'

def usdToBtc(willie, usd):
    try:
        data = web.get("https://www.bitstamp.net/api/ticker/", 10)
        decoded = json.loads(data)
        lastTrade = decoded["last"] 
        usdPerBtc = float(lastTrade) * 100
        totalConverted = (SATOSHI*usd)/usdPerBtc
        return totalConverted
    except:
        return "ERROR"

def currentDiff(willie, trigger):
    try:
        diff = web.get("http://blockchain.info/q/getdifficulty")
        willie.say("The current BTC mining difficulty is {}".format(float(diff)))
    except KeyError:
        willie.say("There was an error in retrieving realtime data from the blockchain.")    
    except:
        willie.say("There was an error in retrieving realtime data from the blockchain.")
currentDiff.commands = ['currentdiff', 'diff', 'btc-diff', 'btcdiff', 'diff-btc', 'diffbtc']
currentDiff.priority = 'medium'

def autoDeauth(willie, nick):
    # If nick is authed, deauth them:
    authStatus = getAuthStatus(willie, nick)
    if authStatus == "authed":
        willie.db.tipaccounts.update(nick, {'authed':'no'})
        willie.debug("DEAUTH", "Nick {} was deauthed.".format(nick), 'always')
    elif authStatus == "deauthed":
        willie.debug("DEAUTH", "Nick {} was already deauthed.".format(nick), 'always')
    else:
        willie.debug("DEAUTH", "Nick {} was not deauthed because they are not registered.".format(nick), 'always')

def autoDeauthKick(willie, trigger):
    autoDeauth(willie, trigger.args[1])
    #willie.debug(trigger.event, 'bytes:{} || nick:{} || args:{}'.format(trigger.bytes,trigger.nick,trigger.args),'always')
    # Response:
    #    [KICK] bytes:BANG! || nick:DickieBot || args:['##gen', 'tylercrumpton', 'BANG!']
autoDeauthKick.event = 'KICK'
autoDeauthKick.rule = r'(.*)'
autoDeauthKick.priority = 'high'
def autoDeauthNick(willie, trigger):
    autoDeauth(willie, trigger.nick.lower())
    #willie.debug(trigger.event, 'bytes:{} || nick:{} || args:{}'.format(trigger.bytes,trigger.nick,trigger.args),'always')
    # Response: 
    #    [NICK] bytes:second || nick:first || args:['second']
autoDeauthNick.event = 'NICK'
autoDeauthNick.rule = r'(.*)'
autoDeauthNick.priority = 'high'
def autoDeauthQuit(willie, trigger):
    autoDeauth(willie, trigger.nick.lower())
    #willie.debug(trigger.event, 'bytes:{} || nick:{} || args:{}'.format(trigger.bytes,trigger.nick,trigger.args),'always')
    # Response: 
    #    [QUIT] bytes:Client Quit || nick:tesetsetset || args:['Client Quit']
autoDeauthQuit.event = 'QUIT'
autoDeauthQuit.rule = r'(.*)'
autoDeauthQuit.priority = 'high'
def autoDeauthPart(willie, trigger):
    autoDeauth(willie, trigger.nick.lower())
    #willie.debug(trigger.event, 'bytes:{} || nick:{} || args:{}'.format(trigger.bytes,trigger.nick,trigger.args),'always')
    # Response: 
    #    [PART] bytes:"Quitting IRC." || nick:tylercrumpton || args:['#btctiptest', '"Quitting IRC."']
autoDeauthPart.event = 'PART'
autoDeauthPart.rule = r'(.*)'
autoDeauthPart.priority = 'high'
def autoDeauthKill(willie, trigger):
    autoDeauth(willie, trigger.args[0])
    #willie.debug(trigger.event, 'bytes:{} || nick:{} || args:{}'.format(trigger.bytes,trigger.nick,trigger.args),'always')
    # Response (not tested):
    #    [KILL] bytes:Bang! || nick:FreenodeMod || args:['tylercrumpton', 'BANG!']
autoDeauthKill.event = 'KILL'
autoDeauthKill.rule = r'(.*)'
autoDeauthKill.priority = 'high'
def autoDeauthDisconnect(willie, trigger):
    autoDeauth(willie, trigger.nick.lower())
    willie.debug(trigger.event, 'bytes:{} || nick:{} || args:{}'.format(trigger.bytes,trigger.nick,trigger.args),'always')
autoDeauthDisconnect.event = 'DISCONNECT'
autoDeauthDisconnect.rule = r'(.*)'
autoDeauthDisconnect.priority = 'high'

def setPass(willie, trigger):
    nick = trigger.nick.lower()
    text = trigger.group().split()
    # PrivMsg-only command:
    if isPrivMsg(trigger):
        # make sure a password was provided
        if len(text) != 2:
            willie.say('Wrong number of arguments. (Spaces are not allowed in passwords)')
        else:
            command,password = text
            # check for a user account
            if willie.db.tipaccounts.contains(nick):
                # has a password already been set?
                if willie.db.tipaccounts.get(nick, 'password_hash') == '':
                    # hash and store the password and salt
                    salt = hashlib.sha256(str(random.randrange(0,999999999999999))).hexdigest()
                    password = hashlib.sha256('{}{}'.format(password,salt)).hexdigest()
                    willie.db.tipaccounts.update(nick, {'salt':salt,'password_hash':password,'authed':'yes'})
                    willie.say("Password has been set. Welcome to BitcoinTip!")
                else:
                    # password is already set, try to change password
                    if willie.db.tipaccounts.get(nick, "authed") == 'yes':
                        # we're authed so set the new password
                        salt = hashlib.sha256(str(random.randrange(0,999999999999999))).hexdigest()
                        password = hashlib.sha256('{}{}'.format(password,salt)).hexdigest()
                        willie.db.tipaccounts.update(nick, {'salt':salt,'password_hash':password})
                        willie.say("New password has been set.")
                    else:
                        # do not try to change password if not authed
                        willie.say("You must be auth'ed in order to change your password.")
            else: # no account found
                willie.say("No account found for {}. Create one first with the '!signup' command.")
    elif len(text) == 2:
        willie.say("Did you really just type your password out here for the world to see? Only use this command in a private '/msg'!")
setPass.commands = ['setpass']
setPass.priority = 'medium'

def auth(willie, trigger):
    nick = trigger.nick.lower()
    # PrivMsg-only command:
    if isPrivMsg(trigger):
        text = trigger.group().split()
        if len(text) != 2:
            willie.say('Wrong number of arguments. The format is "!auth <yourpassword>".')
        else:
            command, password = text
            if willie.db.tipaccounts.contains(nick):
                if willie.db.tipaccounts.get(nick, 'authed') == 'yes':
                    willie.say('You are already authed!') 
                else:
                    passwordHash, passwordSalt = willie.db.tipaccounts.get(nick, ['password_hash', 'salt'])
                    isCorrectPassword = False
                    # Check the password against the hashed value in the DB:
                    if hashlib.sha256('{}{}'.format(password,passwordSalt)).hexdigest() == passwordHash:
                        # Auth the user
                        willie.db.tipaccounts.update(nick, {'authed':'yes'})
                        willie.say('You have been authenticated for {}.'.format(nick))
                    else:
                        willie.say('Incorrect password.'.format(nick))
                    
            else:
                willie.say('The user account for {} has not yet been set up. Set up a BitcoinTip account with "!signup"'.format(nick))
auth.commands = ['auth', 'authenticate']
auth.priority = 'medium'

def deauth(willie, trigger):
    nick = trigger.nick.lower()
    # PrivMsg-only command:
    if isPrivMsg(trigger):
        # Auth-only command:
        authStatus = getAuthStatus(willie, nick)
        if authStatus == "authed":
            # Deauth the nick:
            willie.db.tipaccounts.update(nick, {'authed':'no'})
            willie.say('You have been de-authenticated for {}.'.format(nick))
        elif authStatus == "deauthed":
            willie.say('You are already de-authenticated!')
        elif authStatus == "unregistered":
            willie.say('The user account for {} has not yet been set up. Set up a BitcoinTip account with "!signup"'.format(nick))
deauth.commands = ['deauth', 'unauth', 'deauthenticate']
deauth.priority = 'medium'
deauth.example = '!deauth'

def flip(willie, trigger):
    nick = trigger.nick.lower()
    text = trigger.group().split()
    if len(text) != 2 and len(text) != 3:
        willie.say('Wrong number of arguments.')
    else:
        # Auth-only command:
        authStatus = getAuthStatus(willie, nick)
        if authStatus == "authed":
            if len(text) == 2:
                command,amount = text
                unit = 'BTC'
            else:
                command,amount,unit = text
            try:
                intSatoshis = convertToSatoshis(willie, amount, unit)
                if intSatoshis != "ERROR":
                    floatBitcoins = float(intSatoshis) / SATOSHI
                    stringBitcoins = "{:.8f}".format(floatBitcoins).rstrip("0")
                    valid = True
                else:
                    valid = False
            except ValueError:
                willie.say("Amount entered is not a number.")
                valid = False
            if valid and sendPayment(willie, nick, "BitcoinTip", intSatoshis, False):
                if random.randrange(0,2) == 1:
                    prize = 2*intSatoshis
                    willie.say('You win {} BTC!'.format(stringBitcoins))
                    sendPayment(willie, "BitcoinTip", nick, prize, False)
                else:
                    willie.say('You lose {} BTC.'.format(stringBitcoins))
        elif authStatus == "deauthed":
            willie.say('You are not authenticated. You must first authenticate with "/msg BitcoinTip !auth".')
        elif authStatus == "unregistered":
            willie.say('The user account for {} has not yet been set up. Set up a BitcoinTip account with "!signup"'.format(nick))
flip.commands = ['btc-flip', 'btcflip', 'flip-btc', 'flipbtc']
flip.priority = 'medium'
flip.example = '!btcflip 1 BTC'

def getBalance(willie, trigger):
    nick = trigger.nick.lower()
    # PrivMsg-only command:
    if isPrivMsg(trigger):
        # Auth-only command:
        authStatus = getAuthStatus(willie, nick)
        if authStatus == "authed":
            # Retrieve the nick's balance:
            balance = willie.db.tipaccounts.get(nick, 'balance')
            # Display the nick's balance:
            willie.debug("Balance", balance, 'always')
            willie.say("{}'s balance: {} BTC".format(nick,float(balance)/SATOSHI))
            
        elif authStatus == "deauthed":
            willie.say('You are not authenticated. You must first authenticate with "/msg BitcoinTip !auth".')
        elif authStatus == "unregistered":
            willie.say('The user account for {} has not yet been set up. Set up a BitcoinTip account with "!signup"'.format(nick))
getBalance.commands = ['btc-balance', 'btcbalance', 'balance-btc', 'balancebtc', 'balance']
getBalance.priority = 'medium'
getBalance.example = '!balance'

def free(willie, trigger):
    nick = trigger.nick.lower()
    if willie.db.tipaccounts.contains(nick):
        willie.db.tipaccounts.update(nick, {'balance': '100000000'})
free.commands = ['free']
free.priority = 'medium'
free.example = '!free'

# def cyprus(willie, trigger):
    # if willie.db.tipaccounts.contains(trigger.nick):
        # balance = willie.db.tipaccounts.get(trigger.nick, 'balance')
        # if balance > 0.000001:
            # amount = 0.2 * float(balance)
            # sendPayment(willie, trigger.nick, 'BitcoinTip', amount, 'BTC')
            # willie.say("The Cypriot government takes 20% of {}'s balance!".format(trigger.nick)) 
        # else:
            # willie.say("{} doesn't have any money, so the Cypriot government ingores them.".format(trigger.nick)) 
# cyprus.commands = ['cyprus']
# cyprus.priority = 'medium'
# cyprus.example = '!cyprus'

# def test(willie, trigger):
    # willie.msg('memoserv','send tylercrumpton test')
    # willie.msg('memoserv','send tylercrumpton4343 test')
# test.commands = ['test']
# test.priority = 'medium'
    
UNITS_PIZZA = ['pizza', 'pie', 'pizzas', 'pies']
COEFF_PIZZA_USD = 850 # based on a small pizza at dominos
UNITS_SODA = ['soda', 'pop', 'coke', 'beverage', 'drink', 'cola', 'sodas', 'pops', 'cokes', 'beverages', 'drinks', 'colas']
COEFF_SODA_USD = 50 # based on a 12 oz soda from the vending machine
UNITS_BTC = ['btc', 'bitcoin', 'bitcoins']
COEFF_BTC = SATOSHI # one BTC is 10^8 satoshis
UNITS_SATOSHI = ['satoshi', 'satoshis']
COEFF_SATOSHI = 1 # one satoshi is one satoshi!
  
def convertToSatoshis(willie, amount, unit):
    floatAmount = float(amount)

    if unit.lower() in UNITS_BTC:
        coeff = COEFF_BTC
    elif unit.lower() in UNITS_SATOSHI:
        coeff = COEFF_SATOSHI
    elif unit.lower() in UNITS_PIZZA:
        coeff = usdToBtc(willie, COEFF_PIZZA_USD)
    elif unit.lower() in UNITS_SODA:
        coeff = usdToBtc(willie, COEFF_SODA_USD)
    else:
        willie.say("Invalid units. Try 'BTC', 'pizza', or 'soda'!")
        return "ERROR"
        
    if coeff == "ERROR":
        willie.say("Could not pull realtime BTC value from Bitstamp. Please try again later or use 'BTC' for units")
        return "ERROR"  

    floatSatoshis = floatAmount * coeff
    intSatoshis = int(floatSatoshis + 0.5)
    return intSatoshis
  
def sendPayment(willie, fromNick, toNick, intSatoshis, reqVerified):
    authStatus = getAuthStatus(willie, fromNick)
    if authStatus == "deauthed":
        willie.say('You are not authenticated. You must first authenticate with "/msg BitcoinTip !auth".')
        return False
    elif authStatus == "unregistered":
        willie.say('You do not yet have an account with me. Create one with the "!signup" command.')
        return False
    else:
        currentFromBalance = int(willie.db.tipaccounts.get(fromNick, 'balance'))
        if currentFromBalance < intSatoshis:
            willie.say("Insufficient funds.")
            return False
        elif intSatoshis < 1:
            willie.say("Amount must be at least one satoshi (0.00000001 BTC)")
            return False
        elif not willie.db.tipaccounts.contains(toNick):
            willie.say("{} does not have a BitcoinTip account yet.".format(toNick))
        elif reqVerified and not (willie.db.tipaccounts.get(toNick, 'verified') == "yes"):
            willie.say("{}'s BitcoinTip account is not verified yet.".format(toNick))
        else:
            newFromBalance = currentFromBalance - intSatoshis
            willie.db.tipaccounts.update(fromNick, {'balance': str(newFromBalance)})
            currentToBalance = int(willie.db.tipaccounts.get(toNick, 'balance'))
            newToBalance = intSatoshis + currentToBalance
            willie.db.tipaccounts.update(toNick, {'balance': str(newToBalance)})

            return True

def getAuthStatus(willie, nick):
    # BitcoinTip is always authed:
    if nick == "BitcoinTip" and willie.nick == nick:
        return "authed"
    # If nick has an account:
    elif willie.db.tipaccounts.contains(nick):
        # If nick is authed:
        if willie.db.tipaccounts.get(nick, 'authed') == 'yes':
            return "authed"
        # If nick is not authed:
        else:
            return "deauthed"
    # If nick does not have an account:
    else:
        # User account has not been registered:
        return "unregistered"
        
def isPrivMsg(trigger):
    return (trigger.nick == trigger.sender)

if __name__ == "__main__":
    print __doc__.strip()