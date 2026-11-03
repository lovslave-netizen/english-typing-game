// 영어 타자 게임 점수판 (Google Apps Script 웹앱)
// 점수는 이 스크립트가 붙어 있는 구글 시트의 '점수' 시트에만 쌓여요.
// 설정 방법은 README.md 를 봐 주세요.

var SHEET_NAME = "점수";
var MAX_SCORE = 100000;

function getSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  if (sheet.getLastRow() === 0) sheet.appendRow(["날짜", "이름", "점수", "구분"]);
  return sheet;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// 구분이 없는 옛 기록은 영어 타자 점수로 봐요. 구분: "영어" 또는 "한글"
function modeOf_(v) {
  return v === "한글" ? "한글" : "영어";
}

// 게임 페이지가 점수판을 읽을 때: 구분(영어/한글)별 상위 50명. ?mode=한글 처럼 받아요
function doGet(e) {
  var mode = modeOf_(e && e.parameter ? e.parameter.mode : "");
  var rows = getSheet_().getDataRange().getValues().slice(1).filter(function (r) {
    return modeOf_(String(r[3] || "")) === mode;
  });
  rows.sort(function (a, b) { return Number(b[2]) - Number(a[2]); });
  var top = rows.slice(0, 50).map(function (r) {
    return { name: String(r[1]), score: Number(r[2]) };
  });
  return json_({ ok: true, top: top });
}

// 게임 페이지가 점수를 저장할 때: { name, score }
function doPost(e) {
  var data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({ ok: false, error: "bad json" });
  }
  var name = String(data.name || "").trim().slice(0, 10);
  var mode = modeOf_(String(data.mode || ""));
  var score = Math.floor(Number(data.score));
  if (!name || !(score >= 0 && score <= MAX_SCORE)) {
    return json_({ ok: false, error: "bad input" });
  }
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    getSheet_().appendRow([new Date(), name, score, mode]);
  } finally {
    lock.releaseLock();
  }
  return json_({ ok: true });
}
