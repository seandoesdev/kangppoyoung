package com.policyfund.notices.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "notice_category")
public class NoticeCategoryEntity {

    @Id
    @Column(name = "`key`")
    private String key;

    private String label;

    /** 화면 배지로 표시하는 실제 문서 종류(예: 공고/참고자료/규정/지침/절차). */
    @Column(name = "doc_type")
    private String docType;

    @Column(name = "doc_title")
    private String docTitle;

    protected NoticeCategoryEntity() {}

    public NoticeCategoryEntity(String key, String label, String docType, String docTitle) {
        this.key = key;
        this.label = label;
        this.docType = docType;
        this.docTitle = docTitle;
    }

    public String getKey() { return key; }
    public String getLabel() { return label; }
    public String getDocType() { return docType; }
    public String getDocTitle() { return docTitle; }
}
