// SPDX-License-Identifier: MIT
//
// TriggerScopeWidget — oscilloscope-style render of decoded trigger log
// traces (G7 from the TunerStudio gap backlog). Stacks one track per
// trace with time on X; digital traces get square-wave strokes, analog
// traces get smooth lines. Annotations land as vertical marks in
// accent_warning when severity != "edge" and text_dim otherwise.

#pragma once

#include <QWidget>

#include "tuner_core/trigger_log_visualization.hpp"

class QPaintEvent;

class TriggerScopeWidget : public QWidget {
public:
    explicit TriggerScopeWidget(QWidget* parent = nullptr);

    void set_snapshot(const tuner_core::trigger_log_visualization::Snapshot& s);
    void clear_snapshot();

protected:
    void paintEvent(QPaintEvent*) override;

private:
    tuner_core::trigger_log_visualization::Snapshot snap_;
};
