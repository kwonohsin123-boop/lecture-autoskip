"""
GetSmart 강의 자동 진행 스크립트 (Playwright)

준비: pip install playwright
사용: python auto_lecture.py
      → 크롬 창이 열리면 로그인하고 강의 플레이어를 엽니다.
        플레이어가 열리는 순간부터 자동으로 진행됩니다.
        (로그인 정보는 gsitm_profile 폴더에 저장되어 다음부터는 로그인 생략)
"""
import re
import time
from playwright.sync_api import sync_playwright

PROFILE_DIR = "./gsitm_profile"          # 로그인 정보가 저장되는 전용 프로필 폴더
HOME_URL = "https://hrdgsitm.getsmart.co.kr/"
PLAYER_RE = re.compile(r"/learn/\d+/player")   # 강의 플레이어 주소 형태
POLL = 3                # 상태 확인 간격(초)
WAIT_AUTO_NEXT = 15     # 영상 종료 후 사이트가 알아서 넘어가길 기다리는 시간(초)
WAIT_AFTER_CLICK = 20   # '다음' 클릭 후 넘어가길 기다리는 시간(초)
NO_VIDEO_LIMIT = 60     # 영상을 이 시간(초) 동안 못 찾으면 종료

ARGS = [
    "--autoplay-policy=no-user-gesture-required",   # 클릭 없이 자동재생 허용
    "--disable-background-timer-throttling",        # 창이 뒤에 있어도 멈추지 않게
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]


def on_dialog(dialog):
    # "다음으로 넘어가시겠습니까?" 같은 브라우저 확인창을 자동으로 '확인'
    print(f"\n  [확인창] {dialog.message!r} → 확인")
    dialog.accept()


def sleep(page, sec):
    # time.sleep 대신 사용: 기다리는 동안에도 확인창 처리가 즉시 이루어짐
    page.wait_for_timeout(sec * 1000)


def wait_for_player(ctx):
    """열린 창들 중 강의 플레이어 주소가 나타날 때까지 대기"""
    print("크롬 창에서 로그인 후 강의 플레이어를 열어주세요. 대기 중...")
    while True:
        pages = [pg for pg in ctx.pages if not pg.is_closed()]
        if not pages:
            return None                     # 브라우저를 닫은 경우
        for pg in pages:
            if PLAYER_RE.search(pg.url):
                print(f"강의 플레이어 감지: {pg.url}")
                return pg
        sleep(pages[0], 1)


def video_state(page):
    """페이지(및 iframe)에서 video 요소 상태를 찾아 반환"""
    for frame in page.frames:
        try:
            st = frame.evaluate("""() => {
                const v = document.querySelector('video');
                if (!v) return null;
                return {src: v.currentSrc, t: v.currentTime, d: v.duration,
                        ended: v.ended, paused: v.paused};
            }""")
        except Exception:
            continue
        if st:
            st["frame"] = frame
            return st
    return None


def try_play(frame):
    try:
        frame.evaluate("() => { const v = document.querySelector('video'); v && v.play().catch(() => {}); }")
    except Exception:
        pass


def click_next(page):
    candidates = [
        page.get_by_role("button", name="다음", exact=True),
        page.get_by_text("다음", exact=True),
    ]
    for loc in candidates:
        try:
            if loc.count() > 0:
                loc.first.click(timeout=3000)
                return True
        except Exception:
            pass
    return False


def wait_change(page, sig, timeout):
    """주소나 영상 소스가 바뀌면 True"""
    end = time.time() + timeout
    while time.time() < end:
        sleep(page, 1)
        st = video_state(page)
        if (page.url, st["src"] if st else None) != sig:
            return True
    return False


def run(page):
    no_video = 0
    while True:
        if page.is_closed():
            print("\n강의 창이 닫혀 종료합니다.")
            return
        st = video_state(page)
        if st is None:
            no_video += POLL
            if no_video >= NO_VIDEO_LIMIT:
                print("\n영상을 찾지 못했습니다. 강의 플레이어 화면인지 확인하세요.")
                return
            sleep(page, POLL)
            continue
        no_video = 0

        ended = st["ended"] or (st["paused"] and st["d"] and st["d"] - st["t"] < 0.5)
        if ended:
            print("\n  영상 종료")
            sig = (page.url, st["src"])
            if not wait_change(page, sig, WAIT_AUTO_NEXT):
                print("  자동으로 넘어가지 않아 '다음' 버튼 클릭")
                if not click_next(page) or not wait_change(page, sig, WAIT_AFTER_CLICK):
                    print("더 이상 넘어가지 않습니다. 모든 강의를 마친 것으로 보고 종료합니다.")
                    return
            print(f"다음 강의로 이동: {page.url}")
            sleep(page, POLL)
            continue

        if st["paused"]:
            try_play(st["frame"])

        print(f"\r  재생 중 {st['t']:.0f} / {st['d'] or 0:.0f}초", end="", flush=True)
        sleep(page, POLL)


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",     # 설치된 크롬 사용(강의 영상 코덱 호환)
            headless=False,
            args=ARGS,
            no_viewport=True,
        )
        ctx.on("page", lambda pg: pg.on("dialog", on_dialog))   # 새 창(팝업)에도 적용
        for pg in ctx.pages:
            pg.on("dialog", on_dialog)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(HOME_URL)

        try:
            player = wait_for_player(ctx)
            if player:
                run(player)
            else:
                print("브라우저가 닫혀 종료합니다.")
        except Exception as e:
            if "closed" in str(e).lower():
                print("\n브라우저가 닫혀 종료합니다.")
            else:
                raise
        finally:
            try:
                ctx.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
