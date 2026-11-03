# Gridiron Nation Auto-Poster (සිංහල මාර්ගෝපදේශය)

මේ bot එක ස්වයංක්‍රීයව:
1. **තරඟයට පැය ~6කට කලින්**: "GAME DAY" image එකක් + title + content + hashtags පෝස්ට් කරනවා.
2. **තරඟයට පැය ~3කට කලින්**: "WHO WINS?" poll පෝස්ට් එකක්. 👍 Like = A කණ්ඩායම, ❤️ Love = Overtime, 😮 Wow = B කණ්ඩායම.
3. **තරඟය ඉවර වී විනාඩි 10-30කට පසු**: "FINAL" image එකක් (ලකුණු සහිත) + title + content + hashtags පෝස්ට් කරනවා.

දත්ත ලබාගන්නේ ESPN හි පොදු scoreboard JSON එකෙන් (NFL සහ College Football). Google search එක scrape කරන්නේ නැහැ, ඒක Google ගේ නීති වලට විරුද්ධයි සහ නිතරම කැඩෙනවා. ESPN එකේ එකම දත්ත ස්ථාවරව ලැබෙනවා.

## ෆයිල් ටික
- `bot.py` : ප්‍රධාන program එක
- `requirements.txt`, `.env.example`, `.gitignore`
- `.github/workflows/bot.yml` : GitHub Actions (නොමිලේ, විනාඩි 10කට වරක් ධාවනය)

## පියවර 1: ඔබේ පරිගණකයේ පරීක්ෂා කිරීම

1. Python 3.10+ ස්ථාපනය කරන්න (python.org). Windows හි install කරද්දී "Add Python to PATH" ටික් කරන්න.
2. ෆෝල්ඩරය විවෘත කරලා Terminal / Command Prompt එකේ:
   ```
   pip install -r requirements.txt
   python bot.py --demo
   ```
3. `out` ෆෝල්ඩරයේ නියැදි image 3ක් හැදෙයි. ඒවා බලන්න. (මේකට Facebook හෝ internet ඕන නැහැ.)
4. ඇත්ත තරඟ වලින් පරීක්ෂා කරන්න (තවමත් Facebook එකට පෝස්ට් නොකරයි):
   ```
   python bot.py --dry-run
   ```

## පියවර 2: Facebook සම්බන්ධ කිරීම
1. `.env.example` ෆයිල් එක `.env` ලෙස copy කරන්න.
2. `FB_PAGE_TOKEN=` ඉදිරියට ඔබේ **Page token** එක දාන්න. (`FB_PAGE_ID` දැනටමත් 939779099218778)
3. Token එකට `pages_manage_posts` සහ `pages_read_engagement` permissions තිබිය යුතුයි.
4. `.env` ෆයිල් එක කිසිවෙකුට/GitHub එකට/chat එකට දෙන්න එපා.
5. ඇත්ත ධාවනය: `python bot.py`

## පියවර 3: ස්වයංක්‍රීයව ධාවනය (විනාඩි 10කට වරක්)

### ක්‍රමය A: GitHub Actions (පරිගණකය on කර තබන්න ඕන නැහැ)
1. github.com හි ගිණුමක් හදලා **Public** repository එකක් සාදන්න. (Private repo එකේ නොමිලේ විනාඩි 2,000ක සීමාව ඉක්මවනවා. Public එකේ සීමාවක් නැහැ. Token එක Secrets වල තියෙන නිසා ආරක්ෂිතයි.)
2. මේ ෆෝල්ඩරයේ ෆයිල් ටික (`.env` හැර) upload කරන්න. `.github/workflows/bot.yml` ෆෝල්ඩර ව්‍යුහය එලෙසම තිබිය යුතුයි.
3. Repository → **Settings → Secrets and variables → Actions → New repository secret**:
   - `FB_PAGE_ID` = 939779099218778
   - `FB_PAGE_TOKEN` = ඔබේ Page token
4. **Actions** tab එකට ගොස් workflow එක enable කරන්න. **Run workflow** ඔබලා එක් වරක් අත්හදා බලන්න.
5. සටහන: GitHub හි schedule කල්ගත වීමක් (විනාඩි කිහිපයක්) සිදුවිය හැකියි.

### ක්‍රමය B: ඔබේ Windows පරිගණකය (always-on නම්)
Task Scheduler → Create Basic Task → Repeat every 10 minutes → Action: `python C:\path\to\gridiron_bot\bot.py`

## සැකසුම් (`.env` හි, අවශ්‍ය නම්)
| නම | තේරුම | default |
|---|---|---|
| PREVIEW_HOURS_BEFORE | තරඟයට පැය කීයකට කලින් | 6 |
| POLL_HOURS_BEFORE | Poll එක තරඟයට පැය කීයකට කලින් | 3 |
| RESULT_DELAY_MINUTES | අවසානයෙන් පසු විනාඩි කීයකට | 10 |
| LEAGUES | nfl,college-football | දෙකම |
| ONLY_TOP25_COLLEGE | College වලින් Top 25 තරඟ පමණක් | true |
| DISPLAY_TZ | image/caption හි වේලා කලාපය | America/New_York |

## අවධානයට
- **Team logos** එකතු කර නැහැ (trademark). Image එක පාට සහ අකුරු වලින් හදන original design එකක්.
- Monetization සඳහා Meta ට අවශ්‍ය original content. Scores පමණක් දැමීමට වඩා ඔබේම විශ්ලේෂණ, අනාවැකි, poll එකතු කරන්න. එයින් engagement වැඩි වෙනවා.
- Token එක කල් ඉකුත් වුණොත් (error 190) අලුත් Page token එකක් ගෙන Secret එක යාවත්කාලීන කරන්න.
- `state.json` මගින් එකම තරඟය දෙවරක් පෝස්ට් වීම වළක්වනවා. එය මකන්න එපා.

## Poll එක ගැන
Facebook Page එකකට සැබෑ (native) poll එකක් API හරහා හදන්න දැන් බැහැ. ඒ නිසා මේ poll එක **Reactions** වලින් ක්‍රියාත්මක වෙනවා: 👍 = A, ❤️ = Overtime, 😮 = B. Votes බලන්න පෝස්ට් එකේ reaction ගණන් බලන්න. (American football හි draw ඉතා කලාතුරකින් සිදුවෙන නිසා, ඒ වෙනුවට "තරඟය Overtime යනවාද?" යන option එක දැමුවා.)
