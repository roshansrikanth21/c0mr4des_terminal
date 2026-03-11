import React, { useState, useRef } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Upload, ScanEye, Loader2, FileImage, CheckCircle, AlertCircle, Target, Send, Paperclip, X } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';

interface AnalysisResult {
    status?: 'success' | 'error';
    error?: string;
    patterns: string[];
    sentiment: string;
    confidence: number;
    recommendation: string;
    analysis: string;
    action_type?: string;
    entry_zone?: string;
    target?: number;
    stop_loss?: number;
    ticker_detected?: string;
}

export function ScanDialog() {
    const [isOpen, setIsOpen] = useState(false);
    const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
    const [previewUrls, setPreviewUrls] = useState<string[]>([]);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [result, setResult] = useState<AnalysisResult | null>(null);
    const [chatQuery, setChatQuery] = useState("");
    const [chatHistory, setChatHistory] = useState<{ role: 'user' | 'assistant', content: string, image?: string }[]>([]);
    const [isChatting, setIsChatting] = useState(false);
    const [chatImage, setChatImage] = useState<File | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const chatFileInputRef = useRef<HTMLInputElement>(null);

    const handleChatSubmit = async () => {
        if (!chatQuery.trim() && !chatImage || !result) return;

        const currentQuery = chatQuery;
        const currentImage = chatImage;

        setChatQuery("");
        setChatImage(null);
        setIsChatting(true);

        setChatHistory(prev => [
            ...prev,
            {
                role: 'user',
                content: currentQuery,
                image: currentImage ? URL.createObjectURL(currentImage) : undefined
            }
        ]);

        try {
            const formData = new FormData();
            formData.append('context', `Analysis: ${result.analysis}\nPatterns: ${result.patterns.join(', ')}\nRecommendation: ${result.recommendation}`);
            formData.append('question', currentQuery);

            if (currentImage) {
                formData.append('file', currentImage);
            }

            const res = await fetch('/api/chat_analysis', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) throw new Error("Chat failed");

            const data = await res.json();
            setChatHistory(prev => [...prev, { role: 'assistant', content: data.answer }]);
        } catch (err) {
            console.error(err);
            toast.error("Failed to get answer");
            setChatHistory(prev => [...prev, { role: 'assistant', content: "Error: Could not connect to analysis server." }]);
        } finally {
            setIsChatting(false);
        }
    };

    const addFiles = (files: FileList | null) => {
        if (!files) return;

        const newFiles: File[] = [];
        const newUrls: string[] = [];

        Array.from(files).forEach(file => {
            if (file.type.startsWith('image/')) {
                newFiles.push(file);
                newUrls.push(URL.createObjectURL(file));
            }
        });

        if (newFiles.length > 0) {
            setSelectedFiles(prev => [...prev, ...newFiles]);
            setPreviewUrls(prev => [...prev, ...newUrls]);
            setResult(null);
        }
    };

    const removeFile = (index: number) => {
        const newFiles = [...selectedFiles];
        const newUrls = [...previewUrls];

        // Revoke URL to prevent memory leaks
        URL.revokeObjectURL(newUrls[index]);

        newFiles.splice(index, 1);
        newUrls.splice(index, 1);

        setSelectedFiles(newFiles);
        setPreviewUrls(newUrls);
        setResult(null);
    };

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        addFiles(e.target.files);
        // Reset input so same file can be selected again
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        addFiles(e.dataTransfer.files);
    };

    const handlePaste = async (e: React.ClipboardEvent) => {
        const items = e.clipboardData.items;
        const dt = new DataTransfer();

        for (const item of items) {
            if (item.type.indexOf('image') !== -1) {
                const file = item.getAsFile();
                if (file) dt.items.add(file);
            }
        }
        addFiles(dt.files);
    };

    const handleAnalyze = async () => {
        if (selectedFiles.length === 0) return;

        setIsAnalyzing(true);
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000);
        try {
            const filesToSend = selectedFiles.slice(0, 4);
            if (selectedFiles.length > filesToSend.length) {
                toast.info(`Using first ${filesToSend.length} charts for faster analysis.`);
            }
            const formData = new FormData();
            // Append all files with same key 'files' for List[UploadFile]
            filesToSend.forEach(file => {
                formData.append('files', file);
            });

            const res = await fetch('/api/analyze', {
                method: 'POST',
                body: formData,
                signal: controller.signal,
            });

            if (!res.ok) throw new Error("Analysis failed");

            const data: AnalysisResult = await res.json();
            setResult(data);
            if (data.status === 'error' || data.error) {
                toast.error(data.recommendation || data.error || "Analysis failed");
            } else {
                toast.success("Analysis Complete");
            }
        } catch (err) {
            console.error(err);
            toast.error("Failed to analyze image");
        } finally {
            clearTimeout(timeoutId);
            setIsAnalyzing(false);
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={setIsOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" className="gap-2 border-primary/20 text-primary hover:bg-primary/10">
                    <ScanEye className="w-4 h-4" />
                    Scan Chart
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-6xl h-[90vh] flex flex-col p-0 gap-0" onPaste={handlePaste}>
                <DialogHeader className="px-6 py-4 border-b border-border bg-background z-10">
                    <DialogTitle className="flex items-center gap-2">
                        <ScanEye className="w-5 h-5 text-primary" />
                        AI Chart Pattern Recognition
                    </DialogTitle>
                </DialogHeader>

                <div className="flex-1 overflow-hidden grid grid-cols-1 lg:grid-cols-12 h-full">
                    {/* LEFT COLUMN: Upload & Thumbnails (3 cols) */}
                    <div className="lg:col-span-3 p-4 border-r border-border bg-secondary/10 flex flex-col gap-4 overflow-y-auto">
                        {/* Upload Area */}
                        <div
                            className={cn(
                                "border-2 border-dashed border-border rounded-lg flex flex-col items-center justify-center text-center cursor-pointer hover:bg-secondary/50 transition-colors p-6 min-h-[150px]",
                                isAnalyzing && "opacity-50 pointer-events-none"
                            )}
                            onClick={() => fileInputRef.current?.click()}
                            onDragOver={handleDragOver}
                            onDrop={handleDrop}
                        >
                            <input
                                type="file"
                                ref={fileInputRef}
                                className="hidden"
                                accept="image/*"
                                multiple
                                onChange={handleFileSelect}
                            />
                            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-2">
                                <Upload className="w-6 h-6 text-primary" />
                            </div>
                            <p className="font-medium text-sm">Upload Charts</p>
                            <p className="text-xs text-muted-foreground mt-1">Multi-select allowed</p>
                        </div>

                        {/* Image Grid */}
                        <div className="flex-1 overflow-y-auto space-y-3">
                            {previewUrls.map((url, idx) => (
                                <div key={idx} className="relative group rounded-lg overflow-hidden border border-border bg-black/20">
                                    <img src={url} alt={`Chart ${idx + 1}`} className="w-full h-auto object-contain" />
                                    {!isAnalyzing && (
                                        <button
                                            onClick={(e) => { e.stopPropagation(); removeFile(idx); }}
                                            className="absolute top-2 right-2 p-1 bg-destructive text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                                        >
                                            <X className="w-3 h-3" />
                                        </button>
                                    )}
                                    <div className="absolute bottom-2 left-2 px-2 py-0.5 bg-black/60 text-white text-[10px] rounded">
                                        Img {idx + 1}
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* Analyze Button */}
                        {selectedFiles.length > 0 && !result && (
                            <Button size="lg" className="w-full gap-2 shadow-lg shadow-primary/20 sticky bottom-0" onClick={handleAnalyze} disabled={isAnalyzing}>
                                {isAnalyzing ? (
                                    <>
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        Analyzing...
                                    </>
                                ) : (
                                    <>
                                        <ScanEye className="w-4 h-4" />
                                        Run Analysis ({selectedFiles.length})
                                    </>
                                )}
                            </Button>
                        )}
                    </div>

                    {/* MIDDLE COLUMN: SUMMARY & ACTION (3 cols) - NEW REQUIREMENT */}
                    <div className="lg:col-span-3 p-4 border-r border-border bg-card flex flex-col gap-4 overflow-y-auto">
                        {result ? (
                            <div className="space-y-6 animate-in fade-in slide-in-from-left-4 duration-500">
                                {/* 1. Giant Action Badge */}
                                <div className={cn(
                                    "rounded-xl p-6 text-center border-2 shadow-lg",
                                    result.action_type?.includes("CALL") ? "bg-green-500/10 border-green-500 text-green-500" :
                                        result.action_type?.includes("PUT") ? "bg-red-500/10 border-red-500 text-red-500" :
                                            "bg-yellow-500/10 border-yellow-500 text-yellow-500"
                                )}>
                                    <span className="block text-xs font-bold uppercase tracking-widest opacity-70 mb-2">Recommendation</span>
                                    <h2 className="text-3xl font-black uppercase tracking-tight leading-none">
                                        {result.action_type || result.recommendation.split(' ')[0]}
                                    </h2>
                                </div>

                                {/* 2. Entry Zone */}
                                <div className="space-y-1">
                                    <label className="text-xs font-bold uppercase text-muted-foreground ml-1">Entry Zone</label>
                                    <div className="p-3 bg-secondary rounded-lg border border-border font-mono text-lg font-bold text-center">
                                        {result.entry_zone || "Watch Price Action"}
                                    </div>
                                </div>

                                {/* 3. Targets & Stops */}
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                                        <div className="flex items-center gap-1.5 text-green-600 dark:text-green-400 mb-1">
                                            <Target className="w-3 h-3" />
                                            <span className="text-[10px] font-bold uppercase">Target</span>
                                        </div>
                                        <div className="text-xl font-bold font-mono text-green-700 dark:text-green-300">
                                            {result.target || "---"}
                                        </div>
                                    </div>
                                    <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                                        <div className="flex items-center gap-1.5 text-red-600 dark:text-red-400 mb-1">
                                            <AlertCircle className="w-3 h-3" />
                                            <span className="text-[10px] font-bold uppercase">Stop Loss</span>
                                        </div>
                                        <div className="text-xl font-bold font-mono text-red-700 dark:text-red-300">
                                            {result.stop_loss || "---"}
                                        </div>
                                    </div>
                                </div>

                                {/* 4. Confidence */}
                                <div className="p-4 bg-secondary/30 rounded-lg">
                                    <div className="flex justify-between items-end mb-2">
                                        <span className="text-xs font-bold text-muted-foreground">AI Confidence</span>
                                        <span className="text-xl font-bold">{(result.confidence * 100).toFixed(0)}%</span>
                                    </div>
                                    <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                                        <div
                                            className={cn("h-full transition-all duration-1000", result.confidence > 0.7 ? "bg-primary" : "bg-yellow-500")}
                                            style={{ width: `${result.confidence * 100}%` }}
                                        />
                                    </div>
                                </div>

                                {/* 5. Ticker Info */}
                                {result.ticker_detected && (
                                    <div className="p-3 border border-border rounded-lg text-center">
                                        <span className="text-[10px] uppercase text-muted-foreground block">Detected Ticker</span>
                                        <span className="font-bold font-mono text-lg">{result.ticker_detected}</span>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-50 text-center p-4">
                                <ScanEye className="w-12 h-12 mb-2" />
                                <p className="text-sm">Analysis Summary will appear here</p>
                            </div>
                        )}
                    </div>

                    {/* RIGHT COLUMN: DETAILED ANALYSIS & CHAT (6 cols) */}
                    <div className="lg:col-span-6 flex flex-col h-full bg-background">
                        {result ? (
                            <>
                                <ScrollArea className="flex-1 p-6">
                                    <div className="prose prose-sm dark:prose-invert max-w-none">
                                        <h3 className="section-header flex items-center gap-2 text-primary">
                                            <FileImage className="w-4 h-4" /> Comprehensive Analysis
                                        </h3>
                                        <div className="p-4 bg-secondary/10 rounded-lg border-l-4 border-primary mt-4 whitespace-pre-wrap leading-relaxed">
                                            {result.analysis}
                                        </div>

                                        <div className="mt-6">
                                            <h4 className="text-xs font-bold uppercase text-muted-foreground mb-3">Detected Patterns</h4>
                                            <div className="flex flex-wrap gap-2">
                                                {result.patterns.map((p, i) => (
                                                    <Badge key={i} variant="secondary" className="px-3 py-1 text-xs">
                                                        <CheckCircle className="w-3 h-3 mr-1 text-primary" />
                                                        {p}
                                                    </Badge>
                                                ))}
                                            </div>
                                        </div>

                                        {/* Chat History */}
                                        {chatHistory.length > 0 && (
                                            <div className="mt-8 border-t border-border pt-6">
                                                <h4 className="text-xs font-bold uppercase text-muted-foreground mb-4">Q&A History</h4>
                                                <div className="space-y-4">
                                                    {chatHistory.map((msg, i) => (
                                                        <div key={i} className={cn("p-3 rounded-lg text-sm", msg.role === 'user' ? "bg-primary/10 ml-8" : "bg-secondary/50 mr-8")}>
                                                            <span className="font-bold block text-[10px] uppercase opacity-50 mb-1">{msg.role === 'user' ? 'You' : 'AI Analyst'}</span>
                                                            {msg.image && (
                                                                <img src={msg.image} alt="Attached" className="h-20 rounded border border-border/50 mb-2" />
                                                            )}
                                                            {msg.content}
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </ScrollArea>

                                {/* Chat Input */}
                                <div className="p-4 border-t border-border bg-secondary/5">
                                    <form
                                        className="flex gap-2 items-end"
                                        onSubmit={(e) => {
                                            e.preventDefault();
                                            handleChatSubmit();
                                        }}
                                    >
                                        <div className="flex-1 flex flex-col gap-2">
                                            {/* Image Preview */}
                                            {chatImage && (
                                                <div className="relative inline-block w-fit">
                                                    <img src={URL.createObjectURL(chatImage)} alt="Preview" className="h-12 rounded border border-border" />
                                                    <button
                                                        type="button"
                                                        onClick={() => setChatImage(null)}
                                                        className="absolute -top-2 -right-2 bg-destructive text-white rounded-full w-4 h-4 flex items-center justify-center text-[10px]"
                                                    >
                                                        ×
                                                    </button>
                                                </div>
                                            )}

                                            <div className="flex gap-2">
                                                <input
                                                    type="file"
                                                    ref={chatFileInputRef}
                                                    className="hidden"
                                                    accept="image/*"
                                                    onChange={(e) => {
                                                        if (e.target.files?.[0]) setChatImage(e.target.files[0]);
                                                    }}
                                                />
                                                <Button
                                                    type="button"
                                                    size="icon"
                                                    variant="ghost"
                                                    className="shrink-0 text-muted-foreground"
                                                    onClick={() => chatFileInputRef.current?.click()}
                                                >
                                                    <Paperclip className="w-4 h-4" />
                                                </Button>

                                                <input
                                                    className="flex-1 bg-transparent border-none text-sm focus:outline-none placeholder:text-muted-foreground/50"
                                                    placeholder="Ask follow-up questions about this setup..."
                                                    value={chatQuery}
                                                    onChange={(e) => setChatQuery(e.target.value)}
                                                    disabled={isChatting}
                                                />
                                            </div>
                                        </div>

                                        <Button size="icon" type="submit" disabled={isChatting || (!chatQuery.trim() && !chatImage)} className="rounded-full h-8 w-8">
                                            {isChatting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                        </Button>
                                    </form>
                                </div>
                            </>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-30 p-10">
                                <FileImage className="w-16 h-16 mb-4" />
                                <p className="text-lg font-medium">Detailed Technical Breakdown</p>
                                <p className="text-sm">Upload charts to generate report</p>
                            </div>
                        )}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
