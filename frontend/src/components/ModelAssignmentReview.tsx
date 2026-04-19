import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Check, X, Server, Brain, Wrench, Sparkles } from "lucide-react";
import type { ModelAssignment } from "@/types/provider";

interface ModelAssignmentReviewProps {
  provider: string;
  endpoint: string;
  assignments: ModelAssignment[] | null;
  onApprove: () => void;
  onReject: () => void;
  disabled?: boolean;
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
  Bob: <Brain className="h-4 w-4" />,
  Mary: <Sparkles className="h-4 w-4" />,
  Sarah: <Wrench className="h-4 w-4" />,
  Jack: <Check className="h-4 w-4" />,
};

const AGENT_COLORS: Record<string, string> = {
  Bob: "bg-blue-100 text-blue-700",
  Mary: "bg-green-100 text-green-700",
  Sarah: "bg-purple-100 text-purple-700",
  Jack: "bg-orange-100 text-orange-700",
};

export function ModelAssignmentReview({
  provider,
  endpoint,
  assignments,
  onApprove,
  onReject,
  disabled = false,
}: ModelAssignmentReviewProps) {
  return (
    <Card className="border-surface-200">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg font-semibold text-surface-900">
          AI Provider Configuration Review
        </CardTitle>
        <div className="flex items-center gap-2 text-sm text-surface-600">
          <Server className="h-4 w-4" />
          <span className="font-medium">{provider}</span>
          <span className="text-surface-400">•</span>
          <code className="text-xs bg-surface-100 px-1.5 py-0.5 rounded">
            {endpoint}
          </code>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Model Assignments Table */}
        <div className="rounded-md border border-surface-200 overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-surface-50">
                <TableHead className="font-medium text-surface-700">
                  Agent
                </TableHead>
                <TableHead className="font-medium text-surface-700">
                  Model
                </TableHead>
                <TableHead className="font-medium text-surface-700">
                  Purpose
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {assignments?.map((assignment) => (
                <TableRow key={assignment.agent}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="secondary"
                        className={`${
                          AGENT_COLORS[assignment.agent] ||
                          "bg-surface-100 text-surface-700"
                        }`}
                      >
                        <span className="mr-1">
                          {AGENT_ICONS[assignment.agent]}
                        </span>
                        {assignment.agent}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell>
                    <code className="text-xs bg-surface-100 px-1.5 py-0.5 rounded font-mono">
                      {assignment.model}
                    </code>
                  </TableCell>
                  <TableCell className="text-sm text-surface-600">
                    {assignment.purpose}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <Button
            variant="outline"
            onClick={onReject}
            disabled={disabled}
            className="border-surface-300"
          >
            <X className="h-4 w-4 mr-2" />
            Change Provider
          </Button>
          <Button
            onClick={onApprove}
            disabled={disabled}
            className="bg-primary hover:bg-primary/90"
          >
            <Check className="h-4 w-4 mr-2" />
            Approve & Continue
          </Button>
        </div>

        {/* Info Note */}
        <p className="text-xs text-surface-500 text-center">
          These settings will be saved and used for all future sessions.
          You can reconfigure at any time by returning to this step.
        </p>
      </CardContent>
    </Card>
  );
}
