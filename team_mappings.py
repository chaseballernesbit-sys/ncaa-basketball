"""
NCAA Team Name Mappings and Normalization
Maps various name formats across sources to a canonical name
"""

# Canonical name -> list of aliases
TEAM_ALIASES = {
    # ACC
    "North Carolina": ["UNC", "North Carolina Tar Heels", "Tar Heels", "N Carolina", "NC"],
    "Duke": ["Duke Blue Devils", "Blue Devils"],
    "Virginia": ["Virginia Cavaliers", "Cavaliers", "UVA"],
    "NC State": ["North Carolina State", "NC State Wolfpack", "Wolfpack", "N.C. State"],
    "Wake Forest": ["Wake Forest Demon Deacons", "Demon Deacons", "Wake"],
    "Clemson": ["Clemson Tigers"],
    "Florida State": ["Florida St.", "FSU", "Florida State Seminoles", "Seminoles"],
    "Louisville": ["Louisville Cardinals", "Cardinals"],
    "Pittsburgh": ["Pitt", "Pittsburgh Panthers", "Panthers"],
    "Syracuse": ["Syracuse Orange", "Orange", "'Cuse"],
    "Boston College": ["BC", "Boston College Eagles", "Eagles"],
    "Georgia Tech": ["Ga Tech", "Georgia Tech Yellow Jackets", "Yellow Jackets", "GT"],
    "Miami FL": ["Miami", "Miami Hurricanes", "Hurricanes", "Miami (FL)"],
    "Notre Dame": ["Notre Dame Fighting Irish", "Fighting Irish", "ND"],
    "Virginia Tech": ["Va Tech", "Virginia Tech Hokies", "Hokies", "VT"],
    "California": ["Cal", "California Golden Bears", "Golden Bears"],
    "SMU": ["Southern Methodist", "SMU Mustangs", "Mustangs"],
    "Stanford": ["Stanford Cardinal"],

    # Big 12
    "Kansas": ["Kansas Jayhawks", "Jayhawks", "KU"],
    "Baylor": ["Baylor Bears", "Bears"],
    "Texas Tech": ["Texas Tech Red Raiders", "Red Raiders", "TTU"],
    "TCU": ["Texas Christian", "TCU Horned Frogs", "Horned Frogs"],
    "Oklahoma State": ["Oklahoma St.", "OSU", "Oklahoma State Cowboys", "Cowboys", "Ok State"],
    "Texas": ["Texas Longhorns", "Longhorns", "UT"],
    "West Virginia": ["West Va", "WVU", "West Virginia Mountaineers", "Mountaineers"],
    "Iowa State": ["Iowa St.", "ISU", "Iowa State Cyclones", "Cyclones"],
    "Kansas State": ["Kansas St.", "K-State", "KSU", "Kansas State Wildcats"],
    "Oklahoma": ["Oklahoma Sooners", "Sooners", "OU"],
    "BYU": ["Brigham Young", "BYU Cougars", "Cougars"],
    "UCF": ["Central Florida", "UCF Knights", "Knights"],
    "Cincinnati": ["Cincy", "Cincinnati Bearcats", "Bearcats"],
    "Houston": ["Houston Cougars"],
    "Arizona": ["Arizona Wildcats", "Wildcats"],
    "Arizona State": ["ASU", "Arizona State Sun Devils", "Sun Devils", "Arizona St."],
    "Colorado": ["Colorado Buffaloes", "Buffaloes", "Buffs"],
    "Utah": ["Utah Utes", "Utes"],

    # Big Ten
    "Michigan": ["Michigan Wolverines", "Wolverines"],
    "Michigan State": ["Michigan St.", "MSU", "Michigan State Spartans", "Spartans"],
    "Ohio State": ["Ohio St.", "OSU", "Ohio State Buckeyes", "Buckeyes"],
    "Indiana": ["Indiana Hoosiers", "Hoosiers", "IU"],
    "Purdue": ["Purdue Boilermakers", "Boilermakers"],
    "Illinois": ["Illinois Fighting Illini", "Fighting Illini", "Illini"],
    "Wisconsin": ["Wisconsin Badgers", "Badgers", "Wisc"],
    "Iowa": ["Iowa Hawkeyes", "Hawkeyes"],
    "Minnesota": ["Minnesota Golden Gophers", "Golden Gophers", "Gophers", "Minn"],
    "Northwestern": ["Northwestern Wildcats", "NW"],
    "Penn State": ["Penn St.", "PSU", "Penn State Nittany Lions", "Nittany Lions"],
    "Rutgers": ["Rutgers Scarlet Knights", "Scarlet Knights"],
    "Maryland": ["Maryland Terrapins", "Terrapins", "Terps"],
    "Nebraska": ["Nebraska Cornhuskers", "Cornhuskers", "Huskers"],
    "UCLA": ["UCLA Bruins", "Bruins"],
    "USC": ["Southern California", "USC Trojans", "Trojans", "Southern Cal"],
    "Oregon": ["Oregon Ducks", "Ducks"],
    "Washington": ["Washington Huskies", "Huskies", "UW"],

    # SEC
    "Kentucky": ["Kentucky Wildcats", "UK", "Cats"],
    "Tennessee": ["Tennessee Volunteers", "Volunteers", "Vols", "Tenn"],
    "Auburn": ["Auburn Tigers", "Tigers"],
    "Alabama": ["Alabama Crimson Tide", "Crimson Tide", "Bama"],
    "Arkansas": ["Arkansas Razorbacks", "Razorbacks", "Hogs", "Ark"],
    "LSU": ["Louisiana State", "LSU Tigers"],
    "Florida": ["Florida Gators", "Gators", "UF"],
    "Georgia": ["Georgia Bulldogs", "Bulldogs", "UGA"],
    "Ole Miss": ["Mississippi", "Ole Miss Rebels", "Rebels"],
    "Mississippi State": ["Miss State", "Mississippi St.", "MSU", "Mississippi State Bulldogs"],
    "Missouri": ["Missouri Tigers", "Mizzou"],
    "South Carolina": ["South Carolina Gamecocks", "Gamecocks", "USC", "S Carolina"],
    "Vanderbilt": ["Vanderbilt Commodores", "Commodores", "Vandy"],
    "Texas A&M": ["Texas A&M Aggies", "Aggies", "TAMU"],
    "Oklahoma": ["Oklahoma Sooners", "Sooners", "OU"],

    # Big East
    "Villanova": ["Villanova Wildcats", "Nova"],
    "UConn": ["Connecticut", "Connecticut Huskies", "Huskies"],
    "Creighton": ["Creighton Bluejays", "Bluejays"],
    "Xavier": ["Xavier Musketeers", "Musketeers"],
    "Providence": ["Providence Friars", "Friars"],
    "Seton Hall": ["Seton Hall Pirates", "Pirates"],
    "Butler": ["Butler Bulldogs"],
    "Marquette": ["Marquette Golden Eagles", "Golden Eagles"],
    "Georgetown": ["Georgetown Hoyas", "Hoyas"],
    "St. John's": ["St John's", "St. John's Red Storm", "Red Storm", "Saint John's"],
    "DePaul": ["DePaul Blue Demons", "Blue Demons"],

    # WCC (Gonzaga Conference)
    "Gonzaga": ["Gonzaga Bulldogs", "Zags"],
    "Saint Mary's": ["St. Mary's", "Saint Mary's Gaels", "Gaels", "St Mary's CA"],
    "San Francisco": ["San Francisco Dons", "Dons", "USF"],
    "Santa Clara": ["Santa Clara Broncos", "Broncos"],
    "Pepperdine": ["Pepperdine Waves", "Waves"],
    "San Diego": ["San Diego Toreros", "Toreros"],
    "Portland": ["Portland Pilots", "Pilots"],
    "Loyola Marymount": ["LMU", "Loyola Marymount Lions", "Lions"],
    "Pacific": ["Pacific Tigers"],

    # Mountain West
    "San Diego State": ["SDSU", "San Diego State Aztecs", "Aztecs"],
    "Nevada": ["Nevada Wolf Pack", "Wolf Pack"],
    "Boise State": ["Boise St.", "Boise State Broncos"],
    "Colorado State": ["Colorado St.", "CSU", "Colorado State Rams", "Rams"],
    "Wyoming": ["Wyoming Cowboys"],
    "New Mexico": ["New Mexico Lobos", "Lobos", "UNM"],
    "UNLV": ["Nevada Las Vegas", "UNLV Rebels", "Rebels"],
    "Fresno State": ["Fresno St.", "Fresno State Bulldogs"],
    "Air Force": ["Air Force Falcons", "Falcons"],
    "Utah State": ["Utah St.", "Utah State Aggies"],

    # American
    "Memphis": ["Memphis Tigers"],
    "Tulane": ["Tulane Green Wave", "Green Wave"],
    "Wichita State": ["Wichita St.", "Wichita State Shockers", "Shockers"],
    "Temple": ["Temple Owls", "Owls"],
    "Tulsa": ["Tulsa Golden Hurricane", "Golden Hurricane"],
    "East Carolina": ["ECU", "East Carolina Pirates"],
    "South Florida": ["USF", "South Florida Bulls", "Bulls"],
    "SMU": ["Southern Methodist", "SMU Mustangs"],
    "Charlotte": ["Charlotte 49ers", "49ers"],
    "UAB": ["Alabama Birmingham", "UAB Blazers", "Blazers"],
    "FAU": ["Florida Atlantic", "FAU Owls"],
    "North Texas": ["UNT", "North Texas Mean Green", "Mean Green"],
    "Rice": ["Rice Owls"],
    "UTSA": ["UT San Antonio", "UTSA Roadrunners", "Roadrunners"],

    # A-10
    "Dayton": ["Dayton Flyers", "Flyers"],
    "VCU": ["Virginia Commonwealth", "VCU Rams"],
    "Saint Louis": ["St. Louis", "Saint Louis Billikens", "Billikens", "SLU"],
    "Richmond": ["Richmond Spiders", "Spiders"],
    "Davidson": ["Davidson Wildcats"],
    "Rhode Island": ["URI", "Rhode Island Rams"],
    "George Mason": ["GMU", "George Mason Patriots", "Patriots"],
    "La Salle": ["LaSalle", "La Salle Explorers", "Explorers"],
    "Duquesne": ["Duquesne Dukes", "Dukes"],
    "Fordham": ["Fordham Rams"],
    "George Washington": ["GW", "George Washington Colonials", "Colonials"],
    "Massachusetts": ["UMass", "Massachusetts Minutemen", "Minutemen"],
    "St. Bonaventure": ["St Bonaventure", "Saint Bonaventure", "Bonnies"],
    "Loyola Chicago": ["Loyola-Chicago", "Loyola Ramblers", "Ramblers"],

    # MVC
    "Drake": ["Drake Bulldogs"],
    "Bradley": ["Bradley Braves", "Braves"],
    "Missouri State": ["Missouri St.", "Missouri State Bears"],
    "Indiana State": ["Indiana St.", "Indiana State Sycamores", "Sycamores"],
    "Southern Illinois": ["SIU", "Southern Illinois Salukis", "Salukis"],
    "Northern Iowa": ["UNI", "Northern Iowa Panthers"],
    "Valparaiso": ["Valpo", "Valparaiso Beacons", "Beacons"],
    "Evansville": ["Evansville Purple Aces", "Purple Aces"],
    "Illinois State": ["Illinois St.", "Illinois State Redbirds", "Redbirds"],
    "Belmont": ["Belmont Bruins"],
    "Murray State": ["Murray St.", "Murray State Racers", "Racers"],
    "UIC": ["Illinois Chicago", "UIC Flames", "Flames"],

    # CAA
    "Charleston": ["College of Charleston", "Charleston Cougars", "Coll of Charleston"],
    "Hofstra": ["Hofstra Pride", "Pride"],
    "Delaware": ["Delaware Fightin' Blue Hens", "Blue Hens"],
    "Drexel": ["Drexel Dragons", "Dragons"],
    "Towson": ["Towson Tigers"],
    "Northeastern": ["Northeastern Huskies"],
    "UNCW": ["UNC Wilmington", "UNC Wilmington Seahawks", "Seahawks"],
    "William & Mary": ["William and Mary", "W&M", "Tribe"],
    "Elon": ["Elon Phoenix", "Phoenix"],
    "James Madison": ["JMU", "James Madison Dukes"],
    "Monmouth": ["Monmouth Hawks", "Hawks"],
    "Stony Brook": ["Stony Brook Seawolves", "Seawolves"],
    "Campbell": ["Campbell Fighting Camels", "Fighting Camels"],
    "Hampton": ["Hampton Pirates"],
    "North Carolina A&T": ["NC A&T", "NC A&T Aggies", "North Carolina A&T Aggies"],

    # Ivy League
    "Princeton": ["Princeton Tigers"],
    "Yale": ["Yale Bulldogs"],
    "Penn": ["Pennsylvania", "Penn Quakers", "Quakers"],
    "Harvard": ["Harvard Crimson", "Crimson"],
    "Cornell": ["Cornell Big Red", "Big Red"],
    "Brown": ["Brown Bears"],
    "Columbia": ["Columbia Lions"],
    "Dartmouth": ["Dartmouth Big Green", "Big Green"],

    # Southern Conference
    "VMI": ["VMI Keydets", "Keydets", "Virginia Military", "Virginia Military Institute"],
    "Wofford": ["Wofford Terriers", "Terriers"],
    "ETSU": ["East Tennessee State", "East Tennessee State Buccaneers", "Buccaneers", "ETSU Buccaneers"],
    "Chattanooga": ["UTC", "Chattanooga Mocs", "Mocs"],
    "Samford": ["Samford Bulldogs"],
    "UNC Greensboro": ["UNCG", "UNC Greensboro Spartans", "Spartans"],
    "Western Carolina": ["Western Carolina Catamounts", "WCU"],
    "The Citadel": ["Citadel", "Citadel Bulldogs"],
    "Mercer": ["Mercer Bears"],

    # Conference USA
    "FIU": ["Florida International", "Florida International Panthers", "Panthers", "Florida Intl"],
    "Middle Tennessee": ["MTSU", "Middle Tennessee Blue Raiders", "Blue Raiders", "Middle Tenn"],
    "Western Kentucky": ["WKU", "Western Kentucky Hilltoppers", "Hilltoppers", "W Kentucky"],
    "Charlotte": ["Charlotte 49ers", "49ers"],
    "UAB": ["UAB Blazers", "Blazers", "Alabama Birmingham"],
    "UTEP": ["Texas El Paso", "UTEP Miners", "Miners"],
    "Rice": ["Rice Owls"],
    "North Texas": ["UNT", "North Texas Mean Green", "Mean Green"],
    "Louisiana Tech": ["LA Tech", "Louisiana Tech Bulldogs"],
    "Florida Atlantic": ["FAU", "Florida Atlantic Owls", "Owls"],
    "Sam Houston": ["Sam Houston State", "Sam Houston Bearkats", "Bearkats", "SHSU"],
    "Kennesaw State": ["Kennesaw", "Kennesaw State Owls"],
    "New Mexico State": ["NMSU", "New Mexico State Aggies"],
    "Jacksonville State": ["Jax State", "Jacksonville State Gamecocks"],

    # Summit League
    "Kansas City": ["UMKC", "Kansas City Roos", "Roos"],
    "South Dakota": ["USD", "South Dakota Coyotes", "Coyotes"],
    "South Dakota State": ["SDSU", "South Dakota State Jackrabbits", "Jackrabbits"],
    "North Dakota": ["UND", "North Dakota Fighting Hawks", "Fighting Hawks"],
    "North Dakota State": ["NDSU", "North Dakota State Bison", "Bison"],
    "Oral Roberts": ["ORU", "Oral Roberts Golden Eagles"],
    "Omaha": ["Nebraska Omaha", "Omaha Mavericks", "Mavericks"],
    "Denver": ["Denver Pioneers", "Pioneers"],
    "St. Thomas": ["St Thomas", "Saint Thomas", "St. Thomas Tommies", "Tommies"],

    # Other Notable Mid-Majors
    "Saint Peter's": ["St. Peter's", "Saint Peter's Peacocks", "Peacocks"],
    "Oral Roberts": ["ORU", "Oral Roberts Golden Eagles"],
    "Iona": ["Iona Gaels"],
    "Furman": ["Furman Paladins", "Paladins"],
    "Vermont": ["Vermont Catamounts", "Catamounts"],
    "UC Irvine": ["UCI", "UC Irvine Anteaters", "Anteaters"],
    "UC San Diego": ["UCSD", "UC San Diego Tritons", "Tritons"],
    "UC Santa Barbara": ["UCSB", "UC Santa Barbara Gauchos", "Gauchos"],
    "UC Davis": ["UC Davis Aggies"],
    "Long Beach State": ["Long Beach St.", "LBSU", "Long Beach State Beach", "Beach"],
    "Hawaii": ["Hawai'i", "Hawaii Rainbow Warriors", "Rainbow Warriors"],
    "New Mexico State": ["NM State", "NMSU", "New Mexico State Aggies"],
    "Grand Canyon": ["GCU", "Grand Canyon Antelopes", "Antelopes"],
    "Liberty": ["Liberty Flames"],
    "Akron": ["Akron Zips", "Zips"],
    "Kent State": ["Kent St.", "Kent State Golden Flashes", "Golden Flashes"],
    "Toledo": ["Toledo Rockets", "Rockets"],
    "Ohio": ["Ohio Bobcats", "Bobcats"],
    "Bowling Green": ["BGSU", "Bowling Green Falcons"],
    "Buffalo": ["Buffalo Bulls"],
    "Northern Illinois": ["NIU", "Northern Illinois Huskies"],
    "Ball State": ["Ball State Cardinals"],
    "Central Michigan": ["CMU", "Central Michigan Chippewas", "Chippewas"],
    "Eastern Michigan": ["EMU", "Eastern Michigan Eagles"],
    "Miami OH": ["Miami (Ohio)", "Miami Ohio", "Miami RedHawks", "RedHawks", "Miami (OH)"],
    "Western Michigan": ["WMU", "Western Michigan Broncos"],
}

# Build reverse lookup (alias -> canonical name)
def _build_reverse_lookup():
    """Build a dictionary from alias to canonical name"""
    reverse = {}
    for canonical, aliases in TEAM_ALIASES.items():
        reverse[canonical.lower()] = canonical
        for alias in aliases:
            reverse[alias.lower()] = canonical
    return reverse

ALIAS_TO_CANONICAL = _build_reverse_lookup()

def normalize_team_name(name: str) -> str:
    """
    Convert any team name format to canonical name.

    Args:
        name: Team name in any format (e.g., "UNC", "North Carolina Tar Heels", etc.)

    Returns:
        Canonical team name (e.g., "North Carolina")
    """
    if not name:
        return name

    # Clean up the name
    clean_name = name.strip()

    # Try direct lookup first
    if clean_name.lower() in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[clean_name.lower()]

    # Try removing common suffixes
    for suffix in [" Wildcats", " Tigers", " Bears", " Bulldogs", " Eagles",
                   " Hawks", " Cougars", " Cardinals", " Ducks", " Huskies",
                   " Seminoles", " Gators", " Razorbacks", " Cavaliers"]:
        test_name = clean_name.replace(suffix, "")
        if test_name.lower() in ALIAS_TO_CANONICAL:
            return ALIAS_TO_CANONICAL[test_name.lower()]

    # Return original if no match found
    return clean_name

def get_all_aliases(canonical_name: str) -> list:
    """Get all aliases for a canonical team name"""
    if canonical_name in TEAM_ALIASES:
        return [canonical_name] + TEAM_ALIASES[canonical_name]
    return [canonical_name]

# Conference mappings for strength multipliers
CONFERENCE_TIERS = {
    # Tier 1: Elite (1.2x multiplier)
    "Big 12": 1.2,
    "SEC": 1.2,
    "Big Ten": 1.2,

    # Tier 2: Strong (1.0x)
    "ACC": 1.0,
    "Big East": 1.0,

    # Tier 3: Mid-Major Elite (0.85x)
    "Mountain West": 0.85,
    "WCC": 0.85,
    "American": 0.85,
    "Atlantic 10": 0.85,
    "MVC": 0.80,

    # Tier 4: Low-Major (0.65x)
    "CAA": 0.65,
    "Ivy League": 0.65,
    "Horizon": 0.65,
    "MAC": 0.65,
    "Sun Belt": 0.65,
    "Big West": 0.65,
    "WAC": 0.60,
    "Southland": 0.55,
    "Big South": 0.55,
    "MAAC": 0.60,
    "Patriot": 0.55,
    "ASUN": 0.60,
    "America East": 0.55,
    "Summit": 0.55,
    "NEC": 0.50,
    "OVC": 0.50,
    "SWAC": 0.45,
    "MEAC": 0.45,
}

def get_conference_multiplier(conference: str) -> float:
    """Get the strength multiplier for a conference"""
    return CONFERENCE_TIERS.get(conference, 0.70)  # Default for unknown conferences
