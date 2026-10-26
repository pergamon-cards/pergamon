MAX_FIELD_VALUE = 1024


def truncate(text, limit):
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"


def embed(card):
    embed = {}
    print("foo")
    
    embed["title"] = card["title"]
    
    embed["url"] = "https://netrunnerdb.com/en/card/" + card["code"]
    
    if card.get("image_url"):
        embed["thumbnail"] = card["image_url"]
    
    print(embed)
    
    type_code = card["type_code"];
    field_header_string = ""
    if type_code == "agenda":
        field_header_string = agenda_header(card)
    elif type_code == "ice":
        field_header_string = ice_header(card)
    elif type_code == "identity":
        field_header_string = identity_header(card)
    else:
        field_header_string = card_header(card)
        
    print(embed)
    
    # card_text = discord_replace(card["text"]);
    card_text = card["text"]
    embed["fields"] = [{"name": field_header_string, "value": truncate(card_text, MAX_FIELD_VALUE)}]
    
    faction_code = card["faction_code"]
    embed["footer"] = ({ "text" : \
        faction_string(faction_code) +
        " \u2022 " +
        pack_string(card["pack_code"]) +
        " #" +
        str(card["position"])
    })
    
    embed["color"] = faction_color(faction_code)
    
    print(embed)
    
    return embed

def agenda_header(card):
    field_header_string = type_string(card["type_code"])
    
    if "keywords" in card.keys():
        field_header_string += ": " + card["keywords"]
    
    field_header_string += \
        " \u2022 " + \
        str(card["advancement_cost"]) + \
        "/" + \
        str(card["agenda_points"])
    
    return field_header_string

def ice_header(card):
    field_header_string = type_string(card["type_code"])
    
    if "keywords" in card.keys():
        field_header_string += ": " + card["keywords"]
    
    field_header_string += \
        " \u2022 Rez: " + \
        str(card["cost"]) + \
        " \u2022 Strength: " + \
        str(card["strength"])
    
    if "trash_cost" in card.keys():
        field_header_string += " \u2022 Trash: " + str(card["trash_cost"])
    
    faction_cost = card["faction_cost"]
    if faction_cost > 0:
        field_header_string += \
            " \u2022 Influence: " + \
            influence_string(faction_cost)
    
    return field_header_string

def identity_header(card):
    field_header_string = type_string(card["type_code"])
    
    if "keywords" in card.keys():
        field_header_string += ": " + card["keywords"]
        
    field_header_string += \
        " \u2022 " + \
        str(card["minimum_deck_size"]) + \
        "/" + \
        str(card["influence_limit"])
        
    if "base_link" in card.keys():
        field_header_string += " \u2022 Link: " + str(card["base_link"])
    
    return field_header_string

def card_header(card):
    field_header_string = type_string(card["type_code"])
    
    if "keywords" in card.keys():
        field_header_string += ": " + card["keywords"]
        
    field_header_string += \
        " \u2022 Cost: " + \
        str(card["cost"])
        
    if "trash_cost" in card.keys():
        field_header_string += " \u2022 Trash: " + str(card["trash_cost"])
        
    faction_cost = card["faction_cost"]
    
    if faction_cost > 0:
        field_header_string += \
            " \u2022 Influence: " + \
            influence_string(faction_cost)
            
    return field_header_string

def influence_string(faction_cost):
    return "".join(["\u25cf" for _ in range(faction_cost)])

def faction_string(code):
    print("faction string fn")
    match code:
        case "anarch":
            return "Anarch"
        case "criminal":
            return "Criminal"
        case "shaper":
            return "Shaper"
        case "nbn":
            return "NBN"
        case "neutral-corp":
            return "Neutral (Corp)"
        case "neutral-runner":
            return "Neutral (Runner)"
        case "jinteki":
            return "Jinteki"
        case "weyland-consortium":
            return "Weyland Consortium"
        case "haas-bioroid":
            return "Haas-Bioroid"
        case s:
            return s

def faction_color(code):
    match code:
        case "anarch":
            return 0xff4500
        case "criminal":
            return 0x4169e1
        case "shaper":
            return 0x32cd32
        case "nbn":
            return 0xff8c00
        case "neutral-corp":
            return 0x808080
        case "neutral-runner":
            return 0x808080
        case "jinteki":
            return 0xdc143c
        case "weyland-consortium":
            return 0x006400
        case "haas-bioroid":
            return 0x8a2be2
        case s:
            return 0x404040

def type_string(code):
    match code:
        case "agenda":
            return "Agenda"
        case "asset":
            return "Asset"
        case "event":
            return "Event"
        case "hardware":
            return "Hardware"
        case "ice":
            return "Ice"
        case "identity":
            return "Identity"
        case "operation":
            return "Operation"
        case "program":
            return "Program"
        case "resource":
            return "Resource"
        case "upgrade":
            return "Upgrade"
        case s:
            return s

def pack_string(code):
    print("pack string fn")
    match code:
        case "23s":
            return "Flashpoint (23 Seconds)"
        case "asis":
            return "Genesis (A Study in Static)"
        case "atr":
            return "Lunar (All That Remains)"
        case "baw":
            return "Red Sand (Blood and Water)"
        case "bb":
            return "SanSan (Breaker Bay)"
        case "bf":
            return "Mumbad (Business First)"
        case "bm":
            return "Flashpoint (Blood Money)"
        case "cac":
            return "Creation and Control"
        case "cc":
            return "SanSan (Chrome City)"
        case "cd":
            return "Red Sand (Crimson Dust)"
        case "ce":
            return "Genesis (Cyber Exodus)"
        case "core":
            return "Core Set"
        case "core2":
            return "Revised Core Set"
        case "cotc":
            return "Kitara (Council of the Crest)"
        case "dad":
            return "Data and Destiny"
        case "dag":
            return "Mumbad (Democracy and Dogma)"
        case "dc":
            return "Red Sand (Daedalus Complex)"
        case "df":
            return "Ashes (Downfall)"
        case "draft":
            return "Draft"
        case "dt":
            return "Spin (Double Time)"
        case "dtwn":
            return "Kitara (Down the White Nile)"
        case "eas":
            return "Red Sand (Earth's Scion)"
        case "elev":
            return "Elevation"
        case "es":
            return "Flashpoint (Escalation)"
        case "fal":
            return "Spin (Fear and Loathing)"
        case "fc":
            return "Lunar (First Contact)"
        case "fm":
            return "Red Sand (Free Mars)"
        case "fp":
            return "Genesis (Future Proof)"
        case "ftm":
            return "Mumbad (Fear the Masses)"
        case "hap":
            return "Honor and Profit"
        case "hs":
            return "Genesis (Humanity's Shadow)"
        case "in":
            return "Flashpoint (Intervention)"
        case "ka":
            return "Kitara (Kampala Ascendent)"
        case "kg":
            return "Mumbad (Kala Ghoda)"
        case "ml":
            return "Flashpoint (Martial Law)"
        case "mo":
            return "Magnum Opus"
        case "mor":
            return "Magnum Opus Reprint"
        case "ms":
            return "Borealis (Midnight Sun)"
        case "msbp":
            return "Borealis (Midnight Sun Booster Pack)"
        case "mt":
            return "Spin (Mala Tempora)"
        case "napd":
            return "NAPD Multiplayer"
        case "oac":
            return "Order and Chaos"
        case "oh":
            return "SanSan (Old Hollywood)"
        case "om":
            return "Spin (Opening Moves)"
        case "ph":
            return "Borealis (Parhelion)"
        case "qu":
            return "Flashpoint (Quorum)"
        case "rar":
            return "Reign and Reverie"
        case "rwr":
            return "Liberation (Rebellion Without Rehearsal)"
        case "sc19":
            return "System Core 2019"
        case "sg":
            return "System Gateway"
        case "si":
            return "Mumbad (Salsette Island)"
        case "sm":
            return "Salvaged Memories"
        case "so":
            return "Red Sand (Station One)"
        case "ss":
            return "Kitara (Sovereign Sight)"
        case "st":
            return "Spin (Second Thoughts)"
        case "su21":
            return "System Update 2021"
        case "ta":
            return "Genesis (Trace Amount)"
        case "tai":
            return "Liberation (The Automata Initiative)"
        case "tc":
            return "Spin (True Colors)"
        case "td":
            return "Terminal Directive Cards"
        case "tdatd":
            return "Kitara (The Devil and the Dragon)"
        case "tdc":
            return "Terminal Directive Campaign"
        case "tlm":
            return "Mumbad (The Liberated Mind)"
        case "ts":
            return "Lunar (The Source)"
        case "tsb":
            return "Lunar (The Spaces Between)"
        case "uao":
            return "Lunar (Up and Over)"
        case "uot":
            return "SanSan (The Universe of Tomorrow)"
        case "up":
            return "Lunar (Upstalk)"
        case "ur":
            return "Ashes (Uprising)"
        case "urbp":
            return "Ashes (Uprising Booster Pack)"
        case "uw":
            return "SanSan (The Underway)"
        case "val":
            return "SanSan (The Valley)"
        case "win":
            return "Kitara (Whispers in Nalubaale)"
        case "wla":
            return "Genesis (What Lies Ahead)"
        case s:
            return s
