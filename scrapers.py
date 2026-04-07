import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, timedelta

# ==========================================
# PORTAL CONSTANTS (Total Problems Available)
# ==========================================
LC_TOTAL_GLOBAL = 3400 
CF_TOTAL_GLOBAL = 9500

# ==========================================
# 1. LIGHTWEIGHT DATA FETCHING (For Dashboard)
# ==========================================

def get_cf_light(handle):
    """Basic Codeforces rank/rating for the main table."""
    if not handle: return {'platform': 'Codeforces', 'rating': 'N/A', 'rank': 'N/A', 'error': True}
    try:
        url = f"https://codeforces.com/api/user.info?handles={handle}"
        resp = requests.get(url, timeout=5).json()
        if resp.get('status') == 'OK':
            u = resp['result'][0]
            return {'platform': 'Codeforces', 'rating': u.get('rating', 'Unrated'), 'rank': u.get('rank', 'N/A'), 'error': False}
    except: pass
    return {'platform': 'Codeforces', 'rating': 'N/A', 'rank': 'Error', 'error': True}

def get_lc_light(handle):
    """Basic LeetCode ranking for the main table."""
    if not handle: return {'platform': 'LeetCode', 'rating': 'N/A', 'rank': 'N/A', 'error': True}
    query = """query($u: String!) { matchedUser(username: $u) { profile { ranking } } }"""
    try:
        resp = requests.post("https://leetcode.com/graphql", json={'query': query, 'variables': {'u': handle}}, timeout=5).json()
        rank = resp.get('data', {}).get('matchedUser', {}).get('profile', {}).get('ranking', 'N/A')
        return {'platform': 'LeetCode', 'rating': 'N/A', 'rank': rank, 'error': False}
    except: pass
    return {'platform': 'LeetCode', 'rating': 'N/A', 'rank': 'Error', 'error': True}

def get_cc_light(handle):
    """Placeholder for CodeChef to maintain dashboard speed."""
    if not handle: return {'platform': 'CodeChef', 'rating': 'N/A', 'rank': 'N/A', 'error': True}
    return {'platform': 'CodeChef', 'rating': 'View', 'rank': 'Profile', 'error': False}

def get_all_stats(user):
    """Utility for app.py to fetch summary stats."""
    return [get_cf_light(user.cf_handle), get_lc_light(user.lc_handle), get_cc_light(user.cc_handle)]


# ==========================================
# 2. DETAILED DATA FETCHING (For Student Report Card)
# ==========================================

def get_detailed_stats(user):
    """Comprehensive data retrieval for the detailed profile view."""
    stats = {}
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    # --- 1. CODEFORCES DETAILED ---
    if user.cf_handle:
        try:
            info_r = requests.get(f"https://codeforces.com/api/user.info?handles={user.cf_handle}", timeout=5).json()
            info = info_r['result'][0]
            
            subs_r = requests.get(f"https://codeforces.com/api/user.status?handle={user.cf_handle}&from=1&count=500", timeout=5).json()
            subs = subs_r.get('result', [])
            
            # Unique dates for solved problems (filtering for 'OK' only)
            solved_dates = {datetime.fromtimestamp(s['creationTimeSeconds']).strftime('%Y-%m-%d') for s in subs if s.get('verdict') == 'OK'}
            
            # ACCURATE STREAK CALCULATION (Look-back logic)
            cf_streak = 0
            # Start check from today; if no activity today, check yesterday to continue the chain
            check_date = now if today_str in solved_dates else (now - timedelta(days=1))
            while check_date.strftime('%Y-%m-%d') in solved_dates:
                cf_streak += 1
                check_date -= timedelta(days=1)
            
            # 7-Day History Log (Unique problems per day)
            cf_history = []
            for i in range(6, -1, -1):
                d_obj = now - timedelta(days=i)
                d_start = d_obj.replace(hour=0, minute=0, second=0).timestamp()
                d_end = d_start + 86400
                unique_solved_count = len({f"{s['problem']['contestId']}{s['problem']['index']}" for s in subs 
                                         if s.get('verdict') == 'OK' and d_start <= s['creationTimeSeconds'] < d_end})
                cf_history.append({'date': d_obj.strftime('%Y-%m-%d'), 'count': unique_solved_count})

            solved_set = {f"{s['problem']['contestId']}{s['problem']['index']}" for s in subs if s.get('verdict') == 'OK'}
            
            # Fetch last contest safely
            rating_history = requests.get(f"https://codeforces.com/api/user.rating?handle={user.cf_handle}", timeout=5).json().get('result', [])
            last_cf_contest = rating_history[-1]['contestName'] if rating_history else "N/A"

            stats['Codeforces'] = {
                'solved': len(solved_set),
                'total_questions': CF_TOTAL_GLOBAL,
                'solved_percentage': round((len(solved_set) / CF_TOTAL_GLOBAL) * 100, 2) if CF_TOTAL_GLOBAL else 0,
                'today_count': len({f"{s['problem']['contestId']}{s['problem']['index']}" for s in subs if s.get('verdict') == 'OK' and s['creationTimeSeconds'] >= start_of_today}),
                'streak': cf_streak,
                'history': cf_history,
                'rating': info.get('rating', 'Unrated'),
                'rank': info.get('rank', 'Unrated'),
                'last_contest': last_cf_contest,
                'error': False
            }
        except: stats['Codeforces'] = {'error': True}

    # --- 2. LEETCODE DETAILED ---
    if user.lc_handle:
        query = """
        query userDetails($u: String!) {
            matchedUser(username: $u) {
                submitStats { acSubmissionNum { count } }
                userCalendar { submissionCalendar }
            }
            userContestRankingHistory(username: $u) { contest { title } attended }
        }
        """
        try:
            resp = requests.post("https://leetcode.com/graphql", json={'query': query, 'variables': {'u': user.lc_handle}}, timeout=7).json()
            user_data = resp.get('data', {}).get('matchedUser')
            
            if user_data:
                solved = user_data['submitStats']['acSubmissionNum'][0]['count']
                cal = json.loads(user_data['userCalendar']['submissionCalendar'])
                date_counts = {datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d'): cnt for ts, cnt in cal.items()}
                
                # ACCURATE STREAK CALCULATION (Look-back logic)
                lc_streak = 0
                check_date = now if today_str in date_counts else (now - timedelta(days=1))
                while check_date.strftime('%Y-%m-%d') in date_counts:
                    lc_streak += 1
                    check_date -= timedelta(days=1)

                # 7-Day History Log
                lc_history = []
                for i in range(6, -1, -1):
                    d_str = (now - timedelta(days=i)).strftime('%Y-%m-%d')
                    lc_history.append({'date': d_str, 'count': date_counts.get(d_str, 0)})

                contest_history = resp.get('data', {}).get('userContestRankingHistory', [])
                last_c = next((c['contest']['title'] for c in reversed(contest_history) if c.get('attended')), "None")

                stats['LeetCode'] = {
                    'solved': solved,
                    'total_questions': LC_TOTAL_GLOBAL,
                    'solved_percentage': round((solved / LC_TOTAL_GLOBAL) * 100, 2) if LC_TOTAL_GLOBAL else 0,
                    'today_count': date_counts.get(today_str, 0),
                    'streak': lc_streak,
                    'history': lc_history,
                    'last_contest': last_c,
                    'error': False
                }
            else:
                stats['LeetCode'] = {'error': True}
        except: stats['LeetCode'] = {'error': True}

    # --- 3. CODECHEF DETAILED ---
    if user.cc_handle:
        try:
            url = f"https://www.codechef.com/users/{user.cc_handle}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            r = requests.get(url, headers=headers, timeout=8)
            soup = BeautifulSoup(r.content, 'lxml')
            
            rating = soup.find('div', class_='rating-number').text if soup.find('div', class_='rating-number') else "N/A"
            stars = soup.find('span', class_='rating').text if soup.find('span', class_='rating') else "Unrated"
            
            solved = 0
            solved_text = soup.find(string=re.compile(r"Fully Solved"))
            if solved_text:
                match = re.search(r'\((\d+)\)', solved_text.parent.text)
                if match: solved = int(match.group(1))

            stats['CodeChef'] = {
                'rating': rating,
                'rank': stars,
                'solved': solved,
                'error': False
            }
        except: stats['CodeChef'] = {'error': True}

    return stats


# ==========================================
# 3. ASSIGNMENT AUTO-VERIFICATION (SMART MATCH)
# ==========================================

def check_contest_participation(user, contest_name, platform):
    """Smart matcher to check if a student attended a contest."""
    if not contest_name: return False
    
    # 1. Clean the HOD's input: lowercase it and remove platform names
    c_name = contest_name.lower().strip()
    c_name = c_name.replace("leetcode", "").replace("codeforces", "").replace("codechef", "").strip()
    
    # 2. Split into mandatory keywords (e.g., "BIWEEKLY 175" -> ["biweekly", "175"])
    keywords = c_name.split()
    
    if not keywords:
        return False

    if platform == "LeetCode" and user.lc_handle:
        q = """query($u: String!) { userContestRankingHistory(username: $u) { contest { title } attended } }"""
        try:
            r = requests.post("https://leetcode.com/graphql", json={'query': q, 'variables': {'u': user.lc_handle}}, timeout=5).json()
            # Safe .get() to prevent KeyError if the API limits the response
            for rec in r.get('data', {}).get('userContestRankingHistory', []):
                if rec.get('attended'):
                    actual_title = rec['contest']['title'].lower()
                    # Check if ALL keywords typed by the HOD are in the official LeetCode title
                    if all(kw in actual_title for kw in keywords):
                        return True
        except Exception as e: 
            pass

    elif platform == "Codeforces" and user.cf_handle:
        try:
            r = requests.get(f"https://codeforces.com/api/user.rating?handle={user.cf_handle}", timeout=5).json()
            if r.get('status') == 'OK':
                for contest in r.get('result', []):
                    actual_title = contest.get('contestName', '').lower()
                    # Check if ALL keywords typed by the HOD are in the official CF title
                    if all(kw in actual_title for kw in keywords):
                        return True
        except Exception as e:
            pass
            
    return False
