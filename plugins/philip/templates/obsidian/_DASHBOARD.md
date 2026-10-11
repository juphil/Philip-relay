# 메모리 대시보드 (Obsidian 전용)

> 이 파일은 Obsidian에서 Dataview로 렌더되는 감사용 대시보드다. 클로드 메모리가 아니다(회수 대상 아님).
> Obsidian에서 이 노트를 열면 아래 쿼리가 타입별 목록·고아·최근수정으로 자동 렌더된다. raw 텍스트로 보이면 Dataview 플러그인이 켜졌는지 확인.

## 타입별 메모리 (frontmatter metadata.type 기준)

```dataview
TABLE WITHOUT ID file.link AS "메모리", description AS "회수 트리거"
WHERE metadata.type = "feedback"
SORT file.name ASC
```

```dataview
TABLE WITHOUT ID file.link AS "메모리", description AS "요지"
WHERE metadata.type = "project"
SORT file.name ASC
```

```dataview
TABLE WITHOUT ID file.link AS "메모리", description AS "요지"
WHERE metadata.type = "reference" OR metadata.type = "user"
SORT file.name ASC
```

## 최근 수정된 메모리

```dataview
TABLE WITHOUT ID file.link AS "메모리", file.mtime AS "수정"
SORT file.mtime DESC
LIMIT 12
```

## 고아 후보 (들어오는 링크 0 — 연결 검토)

```dataview
LIST
WHERE length(file.inlinks) = 0 AND file.name != "MEMORY" AND file.name != "_DASHBOARD"
SORT file.name ASC
```
