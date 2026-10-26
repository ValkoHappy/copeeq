export const SAMPLES = [
  {
    id: "ank",
    label: "Анкета соискателя",
    sub: "3 фото · есть записи от руки",
    type: "Анкета соискателя",
    pages: [
      ["ank1", "IMG_4021.jpg"],
      ["ank2", "IMG_4022.jpg"],
      ["ank3", "IMG_4023.jpg", 1],
    ],
  },
  {
    id: "zayav",
    label: "Заявление о приёме",
    sub: "1 фото",
    type: "Заявление о приёме на работу",
    pages: [["zayav", "IMG_3310.jpg"]],
  },
  {
    id: "akt",
    label: "Акт с таблицей",
    sub: "PDF · 1 стр. · таблица",
    type: "Акт выполненных работ",
    pages: [["akt", "Акт_14.pdf"]],
  },
  {
    id: "blur",
    label: "Размытое фото",
    sub: "Как выглядит ошибка",
    type: "Анкета соискателя",
    pages: [["ank1", "IMG_4030.jpg", 0, 1]],
  },
];
export const DOUBTS = {
  ank1: [
    {
      id: "d1",
      label: "Ожидаемый доход",
      v: "75 000",
      alts: ["75 000", "76 000", "15 000"],
    },
  ],
  ank2: [
    {
      id: "d2",
      label: "Организация",
      v: "АО «ТомскСнаб»",
      alts: ["АО «ТомскСнаб»", "АО «ТомскСнад»"],
    },
  ],
  ank3: [
    {
      id: "d3",
      label: "Водительский стаж",
      v: "категория В, стаж 6 лет",
      alts: ["категория В, стаж 6 лет", "категория В, стаж 8 лет"],
    },
  ],
};
export const FIELDS = {
  zayav: [
    ["z_from", "От кого"],
    ["z_pos", "Должность"],
    ["z_start", "Дата начала работы"],
    ["z_date", "Дата заявления"],
  ],
  ank1: [
    ["a_tel", "Телефон"],
    ["a_mail", "E-mail"],
    ["a_pos", "Желаемая должность"],
  ],
  ank3: [
    ["a_go", "Когда готовы приступить"],
    ["a_date", "Дата"],
  ],
};
export const SIGS = {
  zayav: [["z_sig", "Подпись заявителя"]],
  ank3: [["a_sig", "Подпись соискателя"]],
  akt: [["k1", "Подпись исполнителя"]],
};
export const TABLES = { ank2: 1, akt: 1 };
export const STEPS = [
  "Изучаем фото",
  "Переносим в Word",
  "Сверяем и доделываем",
];
export const CYCLE = ["ank1", "ank2", "ank3", "zayav", "akt"];
export const APP = [
  "dash",
  "new",
  "processing",
  "result",
  "editor",
  "docs",
  "billing",
  "account",
  "forms",
  "form",
  "examples",
  "faq",
];
export const PRIVATE = [
  "dash",
  "new",
  "processing",
  "result",
  "editor",
  "docs",
  "billing",
  "account",
];
export const FREE = 25;
export const TOAST_ICO = {
  task_alt: "done",
  download: "download",
  error: "error",
  draw: "success",
  check_circle: "success",
  waving_hand: "done",
};
export const now = () => {
  const d = new Date();
  return (
    "Сегодня, " +
    String(d.getHours()).padStart(2, "0") +
    ":" +
    String(d.getMinutes()).padStart(2, "0")
  );
};
export const plural = (n, a, b, c) => {
  const m = n % 10,
    h = n % 100;
  return m === 1 && h !== 11
    ? a
    : m >= 2 && m <= 4 && (h < 10 || h >= 20)
      ? b
      : c;
};
export const kr = (n) => n + " " + plural(n, "кредит", "кредита", "кредитов");
export const tg = (on) => ({
  track: on ? "#1F4EF5" : "#D5D9E4",
  knob: on ? "21px" : "3px",
});
