import { plural } from "../domain/demo-data.js";
export class DocumentListController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  documentListVals() {
    const st = this.store.state;
    const r = st.route;
    const out = {};
    if (r === "docs") {
      const q = st.docsQ.trim().toLowerCase();
      const list = st.docs.filter(
        (d) => !q || d.type.toLowerCase().includes(q),
      );
      const SU = {
        ready: ["Готов", "#E6F6EC", "#15803D"],
        processing: ["Идёт", "#EEF3FF", "#1F4EF5"],
        error: ["Ошибка", "#FDECEC", "#C2272D"],
      };
      Object.assign(out, {
        keepNote:
          "Файлы удаляются автоматически через " +
          st.prefs.keep +
          " " +
          plural(st.prefs.keep, "день", "дня", "дней") +
          " — срок меняется в профиле.",
        docsQ: st.docsQ,
        onDocsQ: (e) => this.store.update({ docsQ: e.target.value }),
        docsEmpty: !list.length,
        docsEmptyTitle: q
          ? "Ничего не нашли по «" + st.docsQ + "»"
          : "Здесь пока пусто",
        docCards: list.map((d) => {
          const su = SU[d.status];
          return {
            key: d.id,
            type: d.type,
            date: d.date,
            page: d.page,
            variant: d.status === "error" ? "photo" : "word",
            blur: d.status === "error",
            stLabel: su[0],
            stBg: su[1],
            stFg: su[2],
            meta:
              d.pages +
              " " +
              plural(d.pages, "страница", "страницы", "страниц") +
              (d.status === "error"
                ? " · " + d.reason + ", не списано"
                : " · удалится через " +
                  d.days +
                  " " +
                  plural(d.days, "день", "дня", "дней")),
            openLabel:
              d.status === "error"
                ? "Переснять"
                : d.status === "processing"
                  ? "Смотреть"
                  : "Открыть",
            canDl: d.status === "ready" && !!d.paid,
            onOpen:
              d.status === "error"
                ? () => this.ports.go("new")
                : this.ports.openDocsDoc(d),
            onDl: () =>
              this.ports.toast(
                "Скачивание: " +
                  d.type.replace(/\s+/g, "_") +
                  ".docx · бесплатно, уже оплачено",
                "download",
              ),
            onDel: () => this.store.update({ modal: "del", delId: d.id }),
          };
        }),
      });
    }
    return out;
  }

  delModalVals() {
    const st = this.store.state;
    const m = st.modal || (st.route === "login" ? "login" : null);
    const out = {};
    if (m === "del") {
      const d = st.docs.find((x) => x.id === st.delId);
      out.mTitle = "Удалить документ сейчас?";
      out.mSub =
        (d ? "«" + d.type + "» " : "") +
        "удалится вместе с исходными фото. Восстановить будет нельзя.";
      out.confirmDel = () => {
        this.store.update((s) => ({
          docs: s.docs.filter((x) => x.id !== s.delId),
          cur: s.cur && s.cur.id === s.delId ? null : s.cur,
          modal: null,
        }));
        this.ports.toast("Документ удалён", "delete");
      };
    }
    return out;
  }
}
