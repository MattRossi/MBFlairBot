import praw
from prawcore.exceptions import NotFound
import trello
import time
import configparser
import unicodedata

########################################
############### CLIENTS ################
########################################

config = configparser.ConfigParser()
config.read('config.properties')
TRELLO_API_KEY = config['TRELLO']['API_KEY']
TRELLO_TOKEN = config['TRELLO']['TOKEN']
TRELLO_FLAIR_REQUESTS_BOARD = config['TRELLO']['FLAIR_REQUESTS_BOARD']
REDDIT_CLIENT_ID = config['REDDIT']['CLIENT_ID']
REDDIT_CLIENT_SECRET = config['REDDIT']['CLIENT_SECRET']
REDDIT_USERNAME = config['REDDIT']['USERNAME']
REDDIT_PASSWORD = config['REDDIT']['PASSWORD']
REDDIT_USER_AGENT = config['REDDIT']['USER_AGENT']
REDDIT_SUBREDDIT = config['REDDIT']['SUBREDDIT']
REDDIT_DEBUG_USER = config['REDDIT']['DEBUG_USER']

trelloClient = trello.TrelloClient(api_key=TRELLO_API_KEY, token=TRELLO_TOKEN)
board = trelloClient.get_board(TRELLO_FLAIR_REQUESTS_BOARD)
new_requests_list = board.list_lists()[1]
completed_requests_list = board.list_lists()[2]
unable_to_complete_list = board.list_lists()[3]

reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    password=REDDIT_PASSWORD,
    user_agent=REDDIT_USER_AGENT,
    username=REDDIT_USERNAME,
)
subreddit = reddit.subreddit(REDDIT_SUBREDDIT)

########################################
################ REDDIT ################
########################################

class FlairTemplate:
    def __init__(self, name, emoji, id, level):
        self.name = name
        self.emoji = emoji
        self.id = id
        self.level = level

class Emojis:
    def __init__(self, name, code):
        self.name = name
        self.code = code

admin_flairs = ['Director', 'Staff', 'Support Team']
supp_flairs = ['College Marcher', 'Drum Corps', 'Military', 'Graduate']
leader_flairs = ['Drum Major', 'Field Commander', 'Captain', 'Section Leader']

flair_templates = []
emojis = []

def get_flair_templates():
    for template in subreddit.flair.templates:
        name = template['richtext'][0]['t'].strip()
        emoji = template['richtext'][1]['a'].strip()
        id = template['id']

        if (any(ext in name for ext in admin_flairs)):
            level = 'Admin'
        elif (any(ext in name for ext in supp_flairs)):
            level = 'Supp'
        elif (any(ext in name for ext in leader_flairs)):
            level = 'Leader'
        else:
            level = 'Basic'
        
        temp = FlairTemplate(name, emoji, id, level)
        flair_templates.append(temp)

def get_emojis():
    for emoji in subreddit.emoji:
        e = Emojis(str(emoji), ':' + str(emoji) + ':')
        emojis.append(e)

def check_for_valid_user(username):
    try:
        reddit.redditor(username).id
    except NotFound:
        return False
    return True

def setFlair(username, flair_text, template_id):
    print('Posting ' + username + '\'s flair with text \'' + flair_text + '\' to reddit using template id ' + template_id)
    subreddit.flair.set(username, flair_text, flair_template_id=template_id)
    print('Posted to reddit!')

def send_emoji_modmail(user_request, collect):
    print(user_request.username)
    message = "Hello!\n\n"
    message += "We received your flair request for **\'{}\'**, but you put **{}** as your emoji. ".format(collect['noEmojiFlairText'], user_request.requestedEmoji)
    message += "Currently, we don't allow for emojis in flairs to include non-listed instruments, so we can do one of the following:\n\n"
    message += "**1)** Add **{}** to the flair so you can use the **{}** emoji (reminder that you can only have a max of 4 flair items!)\n\n".format(user_request.requestedEmoji, user_request.requestedEmoji)
    message += "**2)** Choose from **'{}'** for the emoji for your flair\n\n".format(collect['noEmojiFlairText'])
    message += "**3)** You can resubmit the form to your liking, here: https://marchingband.page.link/flair \n\n"
    message += "Just reply to us here on what you would like to do! \n\n"
    message += "Thanks! - r/marchingband Mod Team"
    subreddit.modmail.create("Flair Issue", message, reddit.redditor(user_request.username))

########################################
################ TRELLO ################
########################################

class UserRequest:
    def __init__(self, username, adminRoles, suppRoles, leaderRoles, basicRoles, requestedEmoji):
        self.username = username
        self.adminRoles = adminRoles
        self.suppRoles = suppRoles
        self.leaderRoles = leaderRoles
        self.basicRoles = basicRoles
        self.requestedEmoji = requestedEmoji

def anyAdminRoles(user):
    if 'Not Applicable' not in user.adminRoles:
        return True
    else:
        return False

def anySuppRoles(user):
    if 'Not Applicable' not in user.suppRoles:
        return True
    else:
        return False

def anyLeaderRoles(user):
    if 'Not Applicable' not in user.leaderRoles:
        return True
    else:
        return False

def anyBasicRoles(user):
    if 'Not Applicable' not in user.basicRoles:
        return True
    else:
        return False

def countBasicRoles(user):
    return len(str(user.basicRoles).split(', '))

def formatFlair(user):
    errors = {
        'isThereAnError': False,
        'types': []
    }
    adminPresent = anyAdminRoles(user)
    suppPresent = anySuppRoles(user)
    leaderPresent = anyLeaderRoles(user)
    basicPresent = anyBasicRoles(user)
    flairText = ' '
    if adminPresent:
        flairText += user.adminRoles[0]
        if suppPresent or leaderPresent or basicPresent:
            flairText += ' - '
    if suppPresent:
        flairText += user.suppRoles[0]
        if adminPresent and (leaderPresent or basicPresent):
            flairText += '; '
        elif leaderPresent or basicPresent:
            flairText += ' - '
    if leaderPresent:
        flairText += user.leaderRoles[0]
        if (adminPresent or suppPresent) and basicPresent:
            flairText += '; '
        elif basicPresent:
            flairText += ' - '
    if basicPresent:
        for role in user.basicRoles:
            flairText += str(role) + ', '
        flairText = flairText.strip()[:-1]

    templ = ''
    if adminPresent:
        templ = find_template(user.adminRoles)
    elif suppPresent:
        templ = find_template(user.suppRoles)
    elif leaderPresent:
        templ = find_template(user.leaderRoles)
    else:
        if user.requestedEmoji not in user.basicRoles:
            print('Ruh roh, that emoji is not in the requested basic roles!')
            errors['isThereAnError'] = True
            errors['types'].append('Emoji')
            return {
                'errors': errors,
                'noEmojiFlairText': flairText
            }
        else:
            templ = find_template([user.requestedEmoji])
    
    flairText += ' ' + templ.emoji
    
    if len(flairText) > 64:
        print("Ruh roh, that flair is too long! It currently has " + str(len(flairText)) + " characters, but we can only have a max of 64 (including the emoji)!")
        errors['isThereAnError'] = True
        errors['types'].append('Character Limit')
        return {
            'errors': errors
        }
    print('Flair Text: ' + flairText)
    print('Template: ' + str(templ.__dict__))
    return {
        'flairText': flairText,
        'template': templ,
        'errors': errors
    }

# TODO Fix this so that Alto Clarinet chooses it's template and not Clarinet's
def find_template(emoji):
    for template in flair_templates:
        if (template.name == emoji[0]):
            return template
    print("Ruh roh, couldn't find the template!")

def get_user_request(card):
    username = ''
    adminRoles = []
    suppRoles = []
    leaderRoles = []
    basicRoles = []
    requestedEmoji = ''

    descriptions = str(card.description).splitlines()
    for line in descriptions:
        line = unicodedata.normalize("NFKD", line)
        temp = line.split('** ')
        if 'From' in line:
            username = temp[1].strip()
        if 'Administrative Role' in line:
            adminRoles.append(temp[1].strip())
        if 'Supplementary Role' in line:
            suppRoles.append(temp[1].strip())
        if 'Student Leader Role' in line:
            leaderRoles.append(temp[1].strip())
        if 'Standard Role' in line:
            basicRoles = temp[1].split(', ')
        if 'Requested Emoji' in line:
            temp = line.split(': **')[1].replace('**', '').strip()
            if '****' in line:
                temp = "Not Applicable"
            requestedEmoji = temp

    user = UserRequest(username, adminRoles, suppRoles, leaderRoles, basicRoles, requestedEmoji)

    print('Username: ' + user.username)
    print('Admin: ' + str(user.adminRoles))
    print('Supp: ' + str(user.suppRoles))
    print('Leader: ' + str(user.leaderRoles))
    print('Basic: ' + str(user.basicRoles))
    print('Emoji: ' + user.requestedEmoji)

    return user

def getRoleCount(user):
    count = 0
    if anyAdminRoles(user):
        count += 1
    if anySuppRoles(user):
        count += 1
    if anyLeaderRoles(user):
        count += 1
    if anyBasicRoles(user):
        count += countBasicRoles(user)
    return count

def get_new_request_count():
    return len(board.list_lists()[1].list_cards())

class TrelloBoardLabels:
    def __init__(self, name, id):
        self.name = name
        self.id = id

boardLabels = []

def get_labels():
    for label in board.get_labels():
        label = TrelloBoardLabels(label.name, label.id)
        boardLabels.append(label)

def find_label(name):
    for label in boardLabels:
        if label.name == name:
            return label

def add_label(card, name):
    card.add_label(find_label(name))

def search_for_previous_cards(name):
    count = 0
    cards = trelloClient.search("name:Flair Request for " + name, board_ids=board.id)
    for card in cards:
        if name in card.name:
            count += 1
    if count == 1:
        return False
    else:
        return True

def mark_card_complete(user_request, card):
    if (search_for_previous_cards(user_request.username)):
        add_label(card, 'Subsequent Request')
    else:
        add_label(card, 'First Request')

    roleCount = getRoleCount(user_request)
    if roleCount == 1:
        add_label(card, 'One Role Combo')
    elif roleCount == 2:
        add_label(card, 'Two Role Combo')
    elif roleCount == 3:
        add_label(card, 'Three Role Combo')
    elif roleCount == 4:
        add_label(card, 'Four Role Combo')
    else:
        print('Ruh roh, there were actually ' + roleCount + ' roles for this user, outside of the 1-4 range')

    card.set_due_complete()
    card.change_list(completed_requests_list.id)
    card.set_pos('top')
    
def mark_card_complete_with_failures(errorTypes, card):
    for item in errorTypes:
        add_label(card, item)

    card.set_due_complete()
    card.change_list(unable_to_complete_list.id)
    card.set_pos('top')

########################################
############## EXECUTIONS ##############
########################################

get_flair_templates()
get_emojis()
get_labels()
errorCount = 0
requestCount = get_new_request_count()
if requestCount != 0:
    for card in new_requests_list.list_cards_iter():
        print("########################")
        user_request = get_user_request(card)
        if (check_for_valid_user(user_request.username)):
            collect = formatFlair(user_request)
            if collect['errors']['isThereAnError']:
                if 'Emoji' in collect['errors']['types']:
                    print('Error was Emoji, so sending Modmail to user!')
                    send_emoji_modmail(user_request, collect)
                mark_card_complete_with_failures(collect['errors']['types'], card)
                errorCount = len(collect['errors']['types'])
            else:
                setFlair(user_request.username, collect['flairText'], collect['template'].id)
                mark_card_complete(user_request, card)
        else:
            print('Ruh roh, could not find the user!')
            mark_card_complete_with_failures(['User Not Found'], card)
        print("########################")
        time.sleep(3)
        print("")
    if errorCount > 0:
        reddit.redditor(REDDIT_DEBUG_USER).message('Flair Bot Errors', str(errorCount) + ' error(s) found today. You should investigate!')
    print('All requests completed!')
else:
    print("No new requests!")