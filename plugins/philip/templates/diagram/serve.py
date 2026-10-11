# -*- coding: utf-8 -*-
# 구조도 로컬 서버 — 이 폴더를 http 로 띄우고, "배치 저장" POST 를 받아 data.js 의
# DEFAULT_POS(배치)·DEFAULT_PORTS(간선 포트 지정)를 직접 갱신한다. 표준 라이브러리만 사용(설치 불필요).
# 실행: start.bat 더블클릭 (또는 python serve.py). 끄기 = 콘솔 창 닫기.
import http.server, socketserver, os, re, json, webbrowser, threading

PORT = 8770
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
DATA = os.path.join(ROOT, "data.js")


def write_default_pos(pos, ports=None):
    with open(DATA, "r", encoding="utf-8") as f:
        text = f.read()
    if "const DEFAULT_POS" not in text:
        raise ValueError("data.js 에서 DEFAULT_POS 를 찾지 못함")
    newjson = json.dumps(pos, ensure_ascii=False)
    text2 = re.sub(r"const DEFAULT_POS = \{.*?\};",
                   lambda m: "const DEFAULT_POS = " + newjson + ";",
                   text, count=1, flags=re.DOTALL)
    if ports is not None:   # 간선 포트 수동 지정. 줄이 없던 파일이면 DEFAULT_POS 뒤에 추가
        pj = json.dumps(ports, ensure_ascii=False)
        if "const DEFAULT_PORTS" in text2:
            text2 = re.sub(r"const DEFAULT_PORTS = \{.*?\};", lambda m: "const DEFAULT_PORTS = " + pj + ";",
                           text2, count=1, flags=re.DOTALL)
        else:
            text2 = re.sub(r"(const DEFAULT_POS = \{.*?\};)", lambda m: m.group(1) + "\nconst DEFAULT_PORTS = " + pj + ";",
                           text2, count=1, flags=re.DOTALL)
    with open(DATA, "w", encoding="utf-8") as f:
        f.write(text2)


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        if self.path != "/save":
            self.send_response(404); self.end_headers(); return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body_in = json.loads(self.rfile.read(n).decode("utf-8"))
            ports = None
            if isinstance(body_in, dict) and "pos" in body_in:   # 새 형식 {pos, ports}. 옛 형식은 pos 만
                pos, ports = body_in["pos"], body_in.get("ports") or {}
            else:
                pos = body_in
            if not isinstance(pos, dict) or not pos:
                raise ValueError("빈 배치")
            write_default_pos(pos, ports)
            body = b"OK"
            self.send_response(200)
        except Exception as e:
            body = str(e).encode("utf-8")
            self.send_response(500)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    url = "http://127.0.0.1:%d/index.html" % PORT
    print("구조도 서버 실행 중:", url)
    print("배치 저장이 이 폴더의 data.js 에 바로 적용됩니다. 끄려면 이 창을 닫으세요.")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
